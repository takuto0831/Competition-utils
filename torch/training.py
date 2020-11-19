import re
import sys
import time
from pathlib import Path
from tqdm import tqdm
from copy import copy, deepcopy

import numpy as np
import pandas as pd

import torch
import torch.utils.data as D
from .snapshot import *
from .logger import *
from .temperature_scaling import *
from .fp16util import network_to_half
from .callback import CallbackEnv, EarlyStopping, SaveModelTrigger, EarlyStoppingTrigger

try:
    from torchsummary import summary
except ModuleNotFoundError:
    print('torch summary not found.')

try:
    import torch_xla
    import torch_xla.core.xla_model as xm
except ModuleNotFoundError:
    print('torch_xla not found.')

try:
    from apex import amp
    from apex.parallel import DistributedDataParallel as DDP
    APEX_FLAG = True
except ModuleNotFoundError:
    print('nvidia apex not found.')
    APEX_FLAG = False


'''
Trainer
'''

class TorchTrainer:
    '''
    Simple Trainer for PyTorch models

    # Usage
    model = Net()
    optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=5e-3)
    NN_FIT_PARAMS = {
        'loader': loader_train,
        'loader_valid': loader_valid,
        'loader_test': loader_test,
        'criterion': nn.BCEWithLogitsLoss(),
        'optimizer': optimizer,
        'scheduler': StepLR(optimizer, step_size=10, gamma=0.9),
        'num_epochs': 100, 
        'stopper': EarlyStopping(patience=20, maximize=True),
        'logger': Logger('results/test/'), 
        'snapshot_path': Path('results/test/nn_best.pt'),
        'eval_metric': auc,
        'info_format': '[epoch] time data loss metric earlystopping',
        'info_train': False,
        'info_interval': 3
    }
    trainer = TorchTrainer(model, serial='test')
    trainer.fit(**NN_FIT_PARAMS)
    '''

    def __init__(self, 
                 model, device=None, serial='Trainer', 
                 fp16=False, xla=False):

        if device is None:
            if xla:
                device = xm.xla_device()
            else:
                device = torch.device(
                    'cuda' if torch.cuda.is_available() else 'cpu')
        
        self.serial = serial
        self.device = device
        self.is_fp16 = fp16 # Automatically use apex if available
        self.is_xla = xla
        self.apex_opt_level = 'O1'
        self.model = model
        self.argument_index_to_model = [0]
        self.argument_index_to_metric = None
        print(f'[{self.serial}] On {self.device}.')

    def model_to_fp16(self):
        if APEX_FLAG:
            self.model, self.optimizer = amp.initialize(
                self.model, self.optimizer, 
                opt_level=self.apex_opt_level, verbosity=0)
            print(f'[{self.serial}] Model, Optimizer -> fp16 (apex)')
        else:
            self.model = network_to_half(self.model)
            print(f'[{self.serial}] Model -> fp16 (simple)')
        
    def model_to_parallel(self):
        if self.is_xla:
            print(
                f'[{self.serial}] Parallel training for xla devices is WIP.')

        if torch.cuda.device_count() > 1:
            all_devices = list(range(torch.cuda.device_count()))
            if self.is_fp16 and APEX_FLAG:
                self.model = nn.parallel.DataParallel(self.model)
            else:
                self.model = nn.parallel.DataParallel(self.model)

            print(f'[{self.serial}] {torch.cuda.device_count()}({all_devices}) gpus found.')

    def train_loop(self, loader, grad_accumulations=1, logger_interval=1):
        loss_total = 0.0
        total_batch = len(loader.dataset) / loader.batch_size
        approx = []
        target = []
        others = []

        self.model.train()
        for batch_i, inputs in enumerate(loader):
            batches_done = len(loader) * self.global_epoch + batch_i

            inputs = [t.to(self.device) for t in inputs]
            y = inputs[-1] # !: the last input is always target
            _y = self.model(*[inputs[i] for i in self.argument_index_to_model])
            if self.is_fp16:
                _y = _y.float()
            
            approx.append(_y.clone().detach())
            target.append(y.clone().detach())
            if self.argument_index_to_metric is not None:
                others.append(inputs[self.argument_index_to_metric].clone().detach())
            
            loss = self.criterion(_y, y)
            if self.is_fp16 and APEX_FLAG:
                with amp.scale_loss(loss, self.optimizer) as scaled_loss:
                    scaled_loss.backward()
            else:
                loss.backward()

            if batch_i == 0:
                # Save output dimension in the first run
                self.out_dim = _y.shape[1:]

            if (batch_i + 1) % grad_accumulations == 0:
                # Accumulates gradient before each step
                loss = loss / grad_accumulations # normalize loss
                if self.is_xla:
                    xm.optimizer_step(self.optimizer, barrier=True)
                else:
                    self.optimizer.step()
                self.optimizer.zero_grad()
                
            if batch_i % logger_interval == 0:
                for param_group in self.optimizer.param_groups:
                    learning_rate = param_group['lr']
                log_train_batch = [
                    (f'batch_loss_train[{self.serial}]', loss.item()),
                    (f'batch_lr_train[{self.serial}]', learning_rate)
                ]
                self.tb_logger.list_of_scalars_summary(log_train_batch, batches_done)

            batch_weight = len(y) / loader.batch_size
            loss_total += loss.item() / total_batch * batch_weight
        
        approx = torch.cat(approx).cpu()
        target = torch.cat(target).cpu()
        if len(others) > 0:
            others = torch.cat(others).cpu()
        if self.eval_metric is None:
            metric_total = -loss_total
        else:
            if len(others) > 0:
                metric_total = self.eval_metric(approx, target, others)
            else:
                metric_total = self.eval_metric(approx, target)
        monitor_metrics_total = []
        for monitor_metric in self.monitor_metrics:
            if len(others) > 0:
                monitor_metrics_total.append(monitor_metric(approx, target, others))
            else:
                monitor_metrics_total.append(monitor_metric(approx, target))

        log_train = [
            (f'epoch_metric_train[{self.serial}]', metric_total),
            (f'epoch_loss_train[{self.serial}]', loss_total)
        ]
        self.tb_logger.list_of_scalars_summary(log_train, self.global_epoch)
        self.log['train']['loss'].append(loss_total)
        self.log['train']['metric'].append(metric_total)
        
        return loss_total, metric_total, monitor_metrics_total

    def valid_loop(self, loader, grad_accumulations=1, logger_interval=1):
        loss_total = 0.0
        total_batch = len(loader.dataset) / loader.batch_size
        approx = []
        target = []
        others = []

        self.model.eval()
        with torch.no_grad():
            for inputs in loader:
                inputs = [t.to(self.device) for t in inputs]
                y = inputs[-1] # !: the last input is always target
                _y = self.model(*[inputs[i] for i in self.argument_index_to_model])
                if self.is_fp16:
                    _y = _y.float()

                approx.append(_y.clone().detach())
                target.append(y.clone().detach())
                if self.argument_index_to_metric is not None:
                    others.append(inputs[self.argument_index_to_metric].clone().detach())

                loss = self.criterion(_y, y)

                batch_weight = len(y) / loader.batch_size
                loss_total += loss.item() / total_batch * batch_weight

        approx = torch.cat(approx).cpu()
        target = torch.cat(target).cpu()
        if len(others) > 0:
            others = torch.cat(others).cpu()
        if self.eval_metric is None:
            metric_total = -loss_total
        else:
            if len(others) > 0:
                metric_total = self.eval_metric(approx, target, others)
            else:
                metric_total = self.eval_metric(approx, target)
        monitor_metrics_total = []
        for monitor_metric in self.monitor_metrics:
            if len(others) > 0:
                monitor_metrics_total.append(monitor_metric(approx, target, others))
            else:
                monitor_metrics_total.append(monitor_metric(approx, target))

        log_valid = [
            (f'epoch_metric_valid[{self.serial}]', metric_total),
            (f'epoch_loss_valid[{self.serial}]', loss_total)
        ]
        self.tb_logger.list_of_scalars_summary(log_valid, self.global_epoch)
        self.log['valid']['loss'].append(loss_total)
        self.log['valid']['metric'].append(metric_total)

        return loss_total, metric_total, monitor_metrics_total

    def predict(self, loader, path=None, test_time_augmentations=1, verbose=True):
        if loader is None:
            print(f'[{self.serial}] No data to predict. Skipping prediction...')
            return None
        prediction = []

        self.model.eval()
        with torch.no_grad():
            for inputs in loader:
                inputs = [t.to(self.device) for t in inputs]
                y = inputs[-1]  # !: the last input is always target
                if self.is_fp16 and APEX_FLAG:
                    with amp.disable_casts():
                        _y = self.model(*[inputs[i] for i in self.argument_index_to_model])
                else:
                    _y = self.model(*[inputs[i] for i in self.argument_index_to_model])
                prediction.append(_y.detach())
        
        prediction = torch.cat(prediction).cpu().numpy()

        if path is not None:
            np.save(path, prediction)

        if verbose:
            print(f'[{self.serial}] Prediction done. exported to {path}')

        return prediction

    def train(self,
            # Essential
            criterion, optimizer, scheduler, 
            loader, num_epochs, loader_valid=None, loader_test=None,
            snapshot_path=None, resume=False,  # Snapshot
            multi_gpu=True, grad_accumulations=1, calibrate_model=False, # Train
            eval_metric=None, monitor_metrics=[], # Evaluation
            test_time_augmentations=1, predict_valid=True, predict_test=True,  # Prediction
            callbacks=[],  # Train add-ons
            # Logger and info
            logger=None, tb_logger=DummyLogger(''), verbose_eval=1
        ):

        if eval_metric is None:
            print(f'[{self.serial}] eval_metric is not set. Inversed criterion will be used instead.')

        self.criterion = criterion
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.eval_metric = eval_metric
        self.monitor_metrics = monitor_metrics
        self.logger = logger
        self.tb_logger = tb_logger
        self.callbacks = callbacks
        self.global_epoch = 0
        self.log = {
            'train': {'loss': [], 'metric': []},
            'valid': {'loss': [], 'metric': []}
        }
        self.outoffold = None
        self.prediction = None

        if snapshot_path is None:
            snapshot_path = Path().cwd()
        if not isinstance(snapshot_path, Path):
            snapshot_path = Path(snapshot_path)
        if len(snapshot_path.suffix) > 0: # file
            self.root_path = snapshot_path.parent
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        else: # dir
            self.root_path = snapshot_path
            snapshot_path = snapshot_path/'snapshot.pt'
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        if not isinstance(self.monitor_metrics, (list, tuple, set)):
            self.monitor_metrics = [self.monitor_metrics]

        self.model.to(self.device)
        if resume:
            load_snapshots_to_model(
                snapshot_path, self.global_epoch, self.model, self.optimizer, self.scheduler,
                self.callbacks, device=self.device)
            if verbose:
                print(
                    f'[{self.serial}] {snapshot_path} is loaded. Continuing from epoch {self.global_epoch}.')
        if self.is_fp16:
            self.model_to_fp16()
        if multi_gpu:
            self.model_to_parallel()

        self.max_epochs = self.global_epoch + num_epochs
        loss_valid, metric_valid = np.inf, -np.inf

        for epoch in range(num_epochs):
            start_time = time.time()
            if self.scheduler.__class__.__name__ == 'ReduceLROnPlateau':
                self.scheduler.step(loss_valid)
            else:
                self.scheduler.step()

            ''' Training '''
            loss_train, metric_train, monitor_metrics_train = \
                self.train_loop(loader, grad_accumulations, 1)

            if loader_valid is None:
                ''' No validation set '''
                early_stopping_target = metric_train
                loss_valid, metric_valid, monitor_metrics_valid = None, None, None

            else:
                ''' Validation '''
                loss_valid, metric_valid, monitor_metrics_valid = \
                    self.valid_loop(loader_valid, grad_accumulations, 1)
                
                early_stopping_target = metric_valid

            # TODO: Callback a posteriori
            ''' Callbacks '''
            for func in self.callbacks + [self.logger._callback]:
                try:
                    func(CallbackEnv(
                        self.serial, 
                        self.model, self.optimizer, self.scheduler, self.criterion,
                        self.eval_metric, epoch, self.global_epoch, self.max_epochs, 
                        early_stopping_target, 
                        loss_train, loss_valid, metric_train, metric_valid, 
                        monitor_metrics_train, monitor_metrics_valid, self.logger
                    ))

                except SaveModelTrigger:
                    ''' Save model '''
                    save_snapshots(snapshot_path,
                        self.global_epoch, self.model,
                        self.optimizer, self.scheduler, self.callbacks)

                except EarlyStoppingTrigger:
                    ''' Early stop '''
                    print('earlkystop')
                    load_snapshots(
                        str(snapshot_path), model=self.model, optimizer=self.optimizer)

                    if calibrate_model:
                        if loader_valid is None:
                            raise ValueError('loader_valid is necessary for calibration.')
                        else:
                            self.calibrate_model(loader_valid)

                    if predict_valid:
                        if loader_valid is None:
                            self.outoffold = self.predict(
                                loader, test_time_augmentations=test_time_augmentations)
                        else:
                            self.outoffold = self.predict(
                                loader_valid, test_time_augmentations=test_time_augmentations)
                    if predict_test:
                        self.prediction = self.predict(
                            loader_test, test_time_augmentations=test_time_augmentations)
                    break

            else:
                '''
                No early stopping
                '''
                self.global_epoch += 1
                continue

            break

        else:  # Not stopped by overfit detector
            print('Not stopped')
            pass
    
    fit = train # for compatibility

    def calibrate_model(self, loader):
        self.model = TemperatureScaler(self.model).to(self.device)
        self.model.set_temperature(loader)
