"""
异常检测算法模型模块
"""

from .spot import SpotDetector
from .three_sigma import ThreeSigmaDetector
from .ewmacontrol_three_sigma import EWMAControlThreeSigmaDetector
from .knn import KNNDetector
__all__ = ['SpotDetector', 'ThreeSigmaDetector', 'EWMAControlThreeSigmaDetector', 'KNNDetector']