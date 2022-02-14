"""
contains classes of the supported models
"""
import os
import numpy as np
import pandas as pd
import pickle
import datetime
import logging
import sklearn.ensemble
import sklearn.svm




class AdvancedThresholdClassifier:
    def __init__(self, y_name, *args, lower_threshold=0, upper_threshold=400, neighborhood=9, moving_average_window_length=9, moving_average_quantile=0.7):#neighborhood_threshold_criterion=lambda x: np.quantile(x, 0.7), **kwargs):
        self.y_name = y_name
        self.lower_threshold=lower_threshold
        self.upper_threshold=upper_threshold
        self.neighborhood=int(neighborhood)
        self.moving_average_window_length= int(moving_average_window_length)
        self.moving_average_quantile=moving_average_quantile
    
    def fit(self, *args, **kwargs):
        pass

    def predict(self, X):
        pred = pd.Series(0, index=X.index)
        pred.loc[X[self.y_name] >= self.upper_threshold] = 1
        
        moving_average = X[self.y_name].rolling(window=self.moving_average_window_length, center=True).quantile(self.moving_average_quantile)

        #neighborhood = 10
        for iter in range(self.neighborhood):
            current_sum = pred.sum()
            direct_neighbors_of_pred = ((np.convolve(pred, [1,0,0], mode="same") | np.convolve(pred, [0,1], mode="same")) & (1-pred)) == 1
            pred.loc[(X[self.y_name] > moving_average) & direct_neighbors_of_pred] = 1
            if current_sum == pred.sum():
                break
        
        pred.loc[X[self.y_name] <= self.lower_threshold] = 1

        return pred

        max_iter = 30
        for idx in pred.loc[(pred == 1) & (X[self.y_name] > 0)].index:
            for _ in range(max_iter):
                idx_iloc = X.index.get_loc(np.where(pred.index == idx)[0][0])
                neighbors = X.iloc[idx_iloc-self.neighborhood:idx_iloc+self.neighborhood]
                neighbors_avg = self.neighborhood_threshold_criterion(X.iloc[[*list(range(idx_iloc-self.neighborhood, idx_iloc)), *list(range(idx_iloc+1, idx_iloc+self.neighborhood))]][self.y_name])
                pred[neighbors.loc[neighbors[self.y_name] > neighbors_avg].index] = 1

        return pred




class AdvancedAutocorrelationClassifier:
    def __init__(self, y_name, slope, prev, next):
        self.y_name = y_name
        
        self.min_prev_pos = int(prev)
        self.max_prev_pos = int(next)
        self.min_prev_neg = int(prev)
        self.max_prev_neg = int(next)
        self.min_next_pos = int(prev)
        self.max_next_pos = int(next)
        self.min_next_neg = int(prev)
        self.max_next_neg = int(next)

        self.slope_threshold = slope
        self.lower_threshold = 0

        self.moving_average_window_length = 15
        self.moving_average_quantile = 0.25
        self.neighborhood = 5
         
    def fit(self, *args, **kwargs):
        pass

    def predict(self, X):
        def slope(x, prev, next):
            diff = (x if next==0 else np.hstack((x[next:], x[-next:]))) - (x if prev==0 else np.hstack((x[:prev], x[:-prev])))

            return diff / (1 if next+prev == 0 else (next+prev))

        pred = pd.Series(0, index=X.index)

        for i in range(self.min_prev_pos, self.max_prev_pos+1):
            for j in range(self.min_next_pos, self.max_next_pos+1):
                pred.loc[slope(X[self.y_name].values, prev=i, next=j) > self.slope_threshold] = 1
                
        for i in range(self.min_prev_neg, self.max_prev_neg+1):
            for j in range(self.min_next_neg, self.max_next_neg+1):
                pred.loc[-slope(X[self.y_name].values, prev=i, next=j) > self.slope_threshold] = 1


        moving_average = X[self.y_name].rolling(window=self.moving_average_window_length, center=True).quantile(self.moving_average_quantile)

        #neighborhood = 10
        for iter in range(self.neighborhood):
            current_sum = pred.sum()
            direct_neighbors_of_pred = ((np.convolve(pred, [1,0,0], mode="same") | np.convolve(pred, [0,1], mode="same")) & (1-pred)) == 1
            pred.loc[(X[self.y_name] > moving_average) & direct_neighbors_of_pred] = 1
            if current_sum == pred.sum():
                break
        
        pred.loc[X[self.y_name] <= self.lower_threshold] = 1

        return pred

        #pred.loc[slope(X[self.y_name].values, prev=self.lag, next=0) > self.slope_threshold] = 1
        #pred.loc[-slope(X[self.y_name].values, prev=0, next=self.lag) > self.slope_threshold] = 1

        pred.loc[X[self.y_name] <= self.lower_threshold] = 1

        return pred




class MyRandomForest(sklearn.ensemble.RandomForestClassifier):
    def __init__(self, y_name, vars, convolve_window_prev, convolve_window_next, *args, **kwargs):
        super().__init__(*args, n_estimators=100, **{k: None if k == "max_depth" and np.isnan(v) else v for k,v in kwargs.items()})
        self.vars = vars
        self.convolve_window_prev = convolve_window_prev
        self.convolve_window_next = convolve_window_next
        
    def fit(self, X, Y):
        X = X[self.vars]
        X = _fill_nan(X)
        X = _convolve(X, self.convolve_window_prev, self.convolve_window_next)

        super().fit(X, Y)

    def predict(self, X):
        X = X[self.vars]
        X = _fill_nan(X)
        X = _convolve(X, self.convolve_window_prev, self.convolve_window_next)
        return super().predict(X)




class MySVC(sklearn.svm.SVC):
    def __init__(self, y_name, vars, convolve_window_prev, convolve_window_next, c):
        super().__init__(C=c, max_iter=100)
        self.c = c
        self.y_name = y_name
        self.vars = vars
        self.convolve_window_prev = convolve_window_prev
        self.convolve_window_next = convolve_window_next
        
    def fit(self, X, Y):
        X = X[self.vars]
        X = _fill_nan(X)
        X = _convolve(X, self.convolve_window_prev, self.convolve_window_next, diffs=True)

        super().fit(X, Y)

    def predict(self, X):
        X = X[self.vars]
        X = _fill_nan(X)
        X = _convolve(X, self.convolve_window_prev, self.convolve_window_next, diffs=True)
        return super().predict(X)




def _fill_nan(X):
    """
    fill nan values with accumulation of prev/next value
    """
    X = X.copy()
    for v in X.columns:
        X[v] = X[v].values[
            np.maximum.accumulate(
                np.where(
                    ~np.isnan(X[v].values),
                    np.arange(np.isnan(X[v].values).shape[0]),
                    np.where(~np.isnan(X[v]))[0][0] if len(np.where(~np.isnan(X[v]))[0]) > 0 else 0
                )
            )
        ]
    X = X.fillna(0)
    return X

def _convolve(X, n_prev, n_next, diffs=False):
    """
    add prev n_prev/next n_next values as columns
    """
    X = X.copy()
    for v in X.columns:
        for i in range(-n_prev,n_next+1):
            v2 = v + "_" + (("n" + str(-i)) if i < 0 else str(i))                
            w = [
                    *([1] if i < 0 else []), 
                    *[0 for _ in range(min(2*(-i if i < 0 else i),len(X)-1))], 
                    *([1] if i >= 0 else [])
                ]
            x = np.convolve(
                X[v],
                w,
                mode="same"
            )
            x[i:]
            X[v2] = x
        
    if diffs:
        cols = X.columns.copy()
        for i,c1 in enumerate(cols[:-1]):
            for c2 in cols[i+1:]:
                #X[c1+"_"+c2+"_ac"] = X.apply(lambda x: (x[c1]/x[c2]) if x[c2] > 0 else 0, axis=1)
                with np.errstate(divide='ignore'):
                    X[c1+"_"+c2+"_ac"] = X[c1] / X[c2]
                    X.loc[X[c2] == 0, c1+"_"+c2+"_ac"] = 0
    return X

