#!/usr/bin/env python3
"""
简单自适应3-Sigma异常检测算法
基于test-time参数优化的轻量级实现
"""

import numpy as np
from base.detector import BaseDetector


class EWMAControlThreeSigmaDetector(BaseDetector):
    
    def __init__(self, 
                 sigma_multiplier=3.0,
                 window_size=50,
                 alpha=0.1,
                 data_pre_required=100,
                 auto_optimize=True):
        """
        初始化检测器
        
        Args:
            sigma_multiplier (float): Sigma倍数，默认3.0
            window_size (int): 滑动窗口大小，默认50
            alpha (float): 指数移动平均权重，默认0.1
            data_pre_required (int): 最少样本数，默认100
            auto_optimize (bool): 是否自动优化参数，默认True
        """
        super().__init__(data_type="univariate")
        
        # 当前参数
        self.sigma_multiplier = sigma_multiplier
        self.window_size = window_size
        self.alpha = alpha
        self.auto_optimize = auto_optimize
        self.data_pre_required = data_pre_required
        
        # 统计量
        self.mean = 0.0
        self.std = 1.0
        self.count = 0
        self.data_buffer = []
        
        # 用于参数优化的数据
        self.optimization_data = []
        self.optimized = False
        
    def _update_statistics(self, value):
        """更新统计量"""
        self.data_buffer.append(value)
        if len(self.data_buffer) > self.window_size:
            self.data_buffer.pop(0)
        
        if self.count >= self.data_pre_required:
            if self.count == 0:
                # 初始化
                self.mean = np.mean(self.data_buffer)
                self.std = np.std(self.data_buffer)
            else:
                # 指数移动平均更新
                current_mean = np.mean(self.data_buffer)
                current_std = np.std(self.data_buffer)
                self.mean = (1 - self.alpha) * self.mean + self.alpha * current_mean
                self.std = (1 - self.alpha) * self.std + self.alpha * current_std
        self.count += 1
    
    def _evaluate_params(self, data, sigma_mult, window_sz, alpha_val):
        """评估参数组合的性能"""
        # 创建临时检测器
        temp_mean = 0.0
        temp_std = 1.0
        temp_buffer = []
        false_positives = 0
        
        for value in data:
            temp_buffer.append(value)
            if len(temp_buffer) > window_sz:
                temp_buffer.pop(0)
            
            if len(temp_buffer) >= self.data_pre_required:
                if temp_mean == 0.0:
                    temp_mean = np.mean(temp_buffer)
                    temp_std = np.std(temp_buffer)
                else:
                    current_mean = np.mean(temp_buffer)
                    current_std = np.std(temp_buffer)
                    temp_mean = (1 - alpha_val) * temp_mean + alpha_val * current_mean
                    temp_std = (1 - alpha_val) * temp_std + alpha_val * current_std
                
                # 检测异常
                if temp_std > 0:
                    z_score = abs(value - temp_mean) / temp_std
                    if z_score > sigma_mult:
                        false_positives += 1
        
        # 返回误报率（越低越好）
        return false_positives / len(data) if len(data) > 0 else 1.0
    
    def _optimize_parameters(self, data):
        if len(data) < self.data_pre_required:
            return
        
        best_score = float('inf')
        best_params = (self.sigma_multiplier, self.window_size, self.alpha)
        
        sigma_values = [2.5, 3.0, 3.5]
        window_values = [30, 50, 80]
        alpha_values = [0.05, 0.1, 0.2]
        
        for sigma_mult in sigma_values:
            for window_sz in window_values:
                for alpha_val in alpha_values:
                    score = self._evaluate_params(data, sigma_mult, window_sz, alpha_val)
                    if score < best_score:
                        best_score = score
                        best_params = (sigma_mult, window_sz, alpha_val)
        
        # 更新参数
        old_window_size = self.window_size
        self.sigma_multiplier, self.window_size, self.alpha = best_params
        self.optimized = True
        
        if self.window_size != old_window_size:
            if len(self.data_buffer) > self.window_size:
                # 保留最新的数据点
                self.data_buffer = self.data_buffer[-self.window_size:]
        
    
    def fit(self, X: np.ndarray, timestamp: int = None, label: int = None):
        """拟合数据"""
        value = X[0]
        
        # 收集用于优化的数据（假设前面的数据都是正常的）
        if not self.optimized and self.auto_optimize:
            self.optimization_data.append(value)
            
            # 达到足够数据量时进行参数优化
            if len(self.optimization_data) >= 100:
                self._optimize_parameters(self.optimization_data)
        
        # 更新统计量
        self._update_statistics(value)
        
        return self
    
    def score(self, X: np.ndarray, timestamp: int = None) -> float:
        """计算异常分数"""
        if self.count < self.data_pre_required:
            return 0.0
        
        if self.std == 0:
            return 0.0
        
        value = X[0]
        z_score = abs(value - self.mean) / self.std
        
        # 返回超出阈值的部分作为异常分数
        return z_score
    
    def predict(self, score: float) -> int:
        """根据分数预测异常"""
        return 1 if score and score > self.sigma_multiplier  else 0
    
    def fit_score(self, X: np.ndarray, timestamp: int = None, label: int = None) -> float:
        """拟合并计算分数"""
        self.fit(X, timestamp, label)
        return self.score(X, timestamp)
    
    def get_params(self) -> dict:
        """获取当前参数"""
        return {
            'sigma_multiplier': self.sigma_multiplier,
            'window_size': self.window_size,
            'alpha': self.alpha,
            'data_pre_required': self.data_pre_required,
            'optimized': self.optimized,
            'current_mean': self.mean,
            'current_std': self.std
        }
    
    def get_threshold(self) -> float:
        """获取当前阈值"""
        return self.sigma_multiplier
    
    def reset(self):
        """重置检测器"""
        self.mean = 0.0
        self.std = 1.0
        self.count = 0
        self.data_buffer = []
        self.optimization_data = []
        self.optimized = False 