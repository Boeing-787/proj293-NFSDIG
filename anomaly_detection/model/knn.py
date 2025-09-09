from collections import deque
from copy import deepcopy

import numpy as np
from scipy.spatial.distance import cdist
from base.detector import BaseDetector


class KNNDetector(BaseDetector):
    def __init__(self, k_neighbor: int = 5, normalize_score: bool = True, **kwargs):
        """Univariate KNN-CAD model with mahalanobis distance :cite:`DBLP:journals/corr/BurnaevI16`.

        Args:
            k_neighbor (int, optional): The number of neighbors to cumulate distances. Defaults to 5.
            normalize_score (bool, optional): Whether to normalize scores. Defaults to True.
        """
        super().__init__(data_type="univariate", **kwargs)
        self.window = deque(maxlen=int(np.sqrt(self.window_len)))
        self.buffer = deque(maxlen=self.window_len - self.window.maxlen)

        assert (
            k_neighbor < self.buffer.maxlen
        ), "k_neighbor must be less than the length of buffer"

        self.k = k_neighbor
        self.scores = []
        self.raw_scores = []  # 存储原始scores用于归一化
        self.threshold = 0.5  # 归一化后的默认阈值
        self.threshold_mode = "percentile"
        self.normalize_score = normalize_score
        
        # 归一化相关参数
        self.score_min = None
        self.score_max = None
        self.score_mean = None
        self.score_std = None

    def fit(self, X: np.ndarray, timestamp: int = None):

        self.window.append(X[0])

        if len(self.window) == self.window.maxlen:
            self.buffer.append(deepcopy(self.window))

        return self

    def score(self, X: np.ndarray, timestamp: int = None) -> float:

        window = deepcopy(self.window)
        window.pop()
        window.append(X[0])

        try:
            dist = cdist(np.array([window]), self.buffer, metric="mahalanobis")[
                0
            ]
        except:
            dist = cdist(
                np.array([window]),
                self.buffer,
                metric="mahalanobis",
                VI=np.linalg.pinv(self.buffer),
            )[0]
        raw_score = np.sum(np.partition(np.array(dist), self.k + 1)[1 : self.k + 1])
        
        # 存储原始score
        self.raw_scores.append(raw_score)
        
        # 归一化处理
        if self.normalize_score:
            normalized_score = self._normalize_score(raw_score)
            self.scores.append(normalized_score)
            return float(normalized_score)
        else:
            self.scores.append(raw_score)
            return float(raw_score)
    
    
    def _normalize_score(self, raw_score: float) -> float:
        """归一化score到[0,1]范围"""
        if len(self.raw_scores) < 10:
            return 0.5  # 初始阶段返回中性值
        
        # 更新归一化参数
        raw_scores_array = np.array(self.raw_scores)
        
        # Min-Max归一化
        if self.score_min is None or self.score_max is None:
            self.score_min = np.min(raw_scores_array)
            self.score_max = np.max(raw_scores_array)
        else:
            # 滑动更新最值
            self.score_min = min(self.score_min, raw_score)
            self.score_max = max(self.score_max, raw_score)
        
        # 避免除零错误
        if self.score_max == self.score_min:
            return 0.5
        
        # Min-Max归一化到[0,1]
        normalized = (raw_score - self.score_min) / (self.score_max - self.score_min)
        return max(0.0, min(1.0, normalized))  # 确保在[0,1]范围内
    
    def _z_score_normalize(self, raw_score: float) -> float:
        """Z-score归一化，然后映射到[0,1]"""
        if len(self.raw_scores) < 10:
            return 0.5
            
        raw_scores_array = np.array(self.raw_scores)
        mean = np.mean(raw_scores_array)
        std = np.std(raw_scores_array)
        
        if std == 0:
            return 0.5
            
        # Z-score标准化
        z_score = (raw_score - mean) / std
        
        # 使用sigmoid函数映射到[0,1]
        normalized = 1 / (1 + np.exp(-z_score))
        return normalized
    
    def predict(self, score: float) -> int:
        # 动态更新阈值
        return 1 if (score and score > 0.5) else 0
    
   
