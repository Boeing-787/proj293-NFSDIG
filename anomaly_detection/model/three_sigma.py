#!/usr/bin/env python3
"""
3-Sigma 异常检测算法实现
"""

import numpy as np
from base.detector import BaseDetector
from collections import deque


class ThreeSigmaDetector(BaseDetector):
    """3-Sigma 异常检测算法
    
    基于正态分布假设的经典统计方法，使用滑动窗口计算均值和标准差，
    将超出 μ ± k*σ 范围的数据点标记为异常。
    """
    
    def __init__(self, window_len: int = 50, multiplier: float = 3.0, **kwargs):
        """
        初始化 3-Sigma 检测器
        
        Args:
            window_len (int): 滑动窗口长度，用于计算统计量
            multiplier (float): sigma 倍数，通常为 2, 2.5, 3 等，默认为 3.0
            **kwargs: 传递给父类的其他参数
        """
        # 首先调用父类的__init__来初始化通用属性，如 self.index
        super().__init__(data_type="univariate")
        
        # 然后用我们自己的、具有固定长度的deque覆盖父类的window
        self.window = deque(maxlen=window_len)
        
        self.multiplier = multiplier
        self.mean = 0.0
        self.std = 0.0
        
    def fit(self, X: np.ndarray, timestamp: int = None):
        """
        拟合数据，更新滑动窗口和统计量
        
        Args:
            X (np.ndarray): 当前观测数据点
            timestamp (int, optional): 时间戳
            
        Returns:
            self: 返回检测器实例
        """
        # 添加新数据点到滑动窗口，deque(maxlen=...) 会自动处理移除旧数据
        self.window.append(X[0])
        
        # 当窗口中有足够数据时，计算统计量
        if len(self.window) >= 2:
            window_data = np.array(self.window)
            self.mean = np.mean(window_data)
            self.std = np.std(window_data, ddof=1)  # 使用样本标准差
        
        return self
    
    def score(self, X: np.ndarray, timestamp: int = None) -> float:
        """
        计算异常分数
        
        Args:
            X (np.ndarray): 当前观测数据点
            timestamp (int, optional): 时间戳
            
        Returns:
            float: 异常分数，表示标准化后的偏离程度
        """
        if self.std == 0 or len(self.window) < 2:
            return 0.0
        
        # 计算 Z-score（标准化分数）
        z_score = abs(X[0] - self.mean) / self.std
        return z_score
    
    def predict(self, score: float) -> int:
        """
        预测是否为异常点
        
        Args:
            X (np.ndarray): 当前观测数据点
            timestamp (int, optional): 时间戳
            
        Returns:
            int: 1 表示异常，0 表示正常
        """
        return 1 if (score and score > self.multiplier) else 0
    
    def get_threshold(self) -> float:
        """
        获取当前的异常检测阈值
        
        Returns:
            float: 阈值（以 sigma 倍数表示）
        """
        return self.multiplier
    
    def set_threshold(self, multiplier: float):
        """
        设置异常检测阈值
        
        Args:
            multiplier (float): 新的 sigma 倍数
        """
        self.multiplier = multiplier
    
    def get_statistics(self) -> dict:
        """
        获取当前的统计信息
        
        Returns:
            dict: 包含均值、标准差、窗口大小等信息
        """
        return {
            'mean': self.mean,
            'std': self.std,
            'window_size': len(self.window),
            'multiplier': self.multiplier,
            'threshold_upper': self.mean + self.multiplier * self.std,
            'threshold_lower': self.mean - self.multiplier * self.std
        }
    
    def reset(self):
        """重置检测器状态"""
        # 创建一个新的实例来重置，确保状态完全干净
        self.__init__(window_len=self.window_len, multiplier=self.multiplier) 