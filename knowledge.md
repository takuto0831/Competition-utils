# codingに関する気づいた点を雑にメモする.

# Categorical Encoding

- OrdinalEncoder: 
categoryを序数に変換する. (1から順番に番号に置き換える) 
categoryの間隔に意味がある場合, 適切ではない可能性がある.

https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OrdinalEncoder.html

# Numerical Encoding

- PowerTransformer (Box-cox, yeo-johnson)
対数変換 (分散安定化変換), yeo-johnsonは負の値がある場合でも

参考: 機械学習のための特徴量エンジニアリング

- QuantileTransformer (rankgauss)

対象となる変数の値を順位づけして, その順位を-1~1にscaling(min-max normalization)