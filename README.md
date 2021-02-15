# Kuma-san's Toolkit 2020

```
　 　 　┼╂┼
　 　 ∩＿┃＿∩
    |ノ      ヽ
   /   ●    ● |
  |     (_●_) ミ        < There is absolutely no warranty. >
 彡､     |∪|  ､｀＼ 
/ ＿＿   ヽノ /´>  )
(＿＿＿）    / (_／
```

## Summary

- 下記のrepositoryを元に, データ分析/機械学習をいち早く行う環境を作成する.

`git clone https://github.com/analokmaus/kuma_utils.git`

- sample dataは下記から用意する.
https://archive.ics.uci.edu/ml/datasets/Adult

# Environment

pyenvを利用した, 仮想環境での利用を想定. (python 3.7.3)

`source ~/python-env/py37env/bin/activate`
`pip install -r reqirements.txt`

## Optional requirements
### xfeat
`pip install -q https://github.com/pfnet-research/xfeat/archive/master.zip`
### Category Encoders
`pip install category_encoders`
### **PyTorch**
For mixed precision training, you must install version `>= 1.6.0` . 
Follow [official instructions](https://pytorch.org/get-started/locally/).
### Pytorch/XLA
Follow [official instructions](https://github.com/pytorch/xla).
### japanize-matplotlib
`pip install japanize-matplotlib`


# Directory
```
┣ visualization
┃   ┣ explore_data              - Simple exploratory data analysis.
┃
┣ preprocessing
┃   ┣ xfeat                     - xfeat modifications.
┃   ┃   ┣ TargetEncoder
┃   ┃   ┣ Pipeline
┃   ┣ DistTransformer           - Distribution transformer for numerical features. 
┃   ┣ LGBMImputer               - Regression imputer for missing values using LightGBM.
┃
┣ training
┃   ┣ Trainer                   - Amazing wrapper for scikit-learn API models.
┃   ┣ CrossValidator            - Amazing cross validation wrapper.
┃   ┣ LGBMLogger                - Logger callback for LightGBM/XGBoost/Optuna.
┃   ┣ StratifiedGroupKFold      - Stratified group k-fold split.
┃   ┣ optuna                    - optuna modifications.
┃       ┣ lightgbm               - Optune lightgbm integration with modifiable n_trials.
┃
┣ metrics                       - Universal metrics
┃   ┣ SeWithFixedSp             - Sensitivity with fixed specificity.
┃   ┣ RMSE
┃   ┣ AUC
┃   ┣ Accuracy
┃   ┣ QWK
┃
┣ torch
    ┣ model_zoo                 - Some basic architectures with pretrained weights.
    ┃   ┣ Xception
    ┃   ┣ SENet
    ┃   ┣ EfficientNet
    ┃ 
    ┣ lr_scheduler
    ┃   ┣ ManualScheduler
    ┃   ┣ CyclicCosAnnealingLR
    ┃   ┣ CyclicLinearLR
    ┃   
    ┣ optimizer
    ┃   ┣ SAM
    ┃ 
    ┣ modules
    ┃   ┃ (activation)
    ┃   ┣ Mish
    ┃   ┃ (pooling)
    ┃   ┣ AdaptiveConcatPool2d/3d
    ┃   ┣ GeM
    ┃   ┃ (attention)
    ┃   ┣ CBAM2d
    ┃   ┃ (normalization)
    ┃   ┣ GroupNorm1d/2d/3d
    ┃   ┣ convert_groupnorm     - Convert all BatchNorm to GroupNorm.
    ┃   ┣ etc...
    ┃ 
    ┣ TorchTrainer              - PyTorch Wrapper.
    ┣ EarlyStopping             - Early stopping callback for TorchTrainer.
    ┣ SaveEveryEpoch            - Save snapshot at the end of every epoch.
    ┣ SaveSnapshot              - Checkpoint callback.
    ┣ TorchLogger               - Logger
    ┣ TensorBoardLogger         - TensorBoard Logger
    ┣ SimpleHook                - Simple train hook for almost all the tasks (see tutorial).
    ┣ TemperatureScaler         - Probability calibration for pytorch models.

```

# Tutorial
- [Exploratory data analysis](examples/Exploratory_data_analysis.ipynb)
- [Data preprocessing](examples/Data_preprocessing.ipynb)
- [Train and validate scikit-learn API models](examples/Train_and_validate_models.ipynb)
- [Train CIFAR-10 (TorchTrainer tutorial)](examples/Train_CIFAR10.md)


# License
The source code in this repository is released under the MIT license.
