#!/usr/bin/env python3
"""
3-Sigma参数优化工具类
提供离线参数优化和分析功能
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

from model.three_sigma import ThreeSigmaDetector
from model.adaptive_three_sigma import AdaptiveThreeSigmaDetector


class ParameterOptimizer:
    """3-Sigma参数优化器
    
    提供全面的参数优化和分析功能，包括：
    - 网格搜索优化
    - 贝叶斯优化
    - 参数敏感性分析
    - 性能对比评估
    """
    
    def __init__(self, 
                 multiplier_range: Tuple[float, float] = (1.0, 5.0),
                 window_range: Tuple[int, int] = (10, 200),
                 optimization_metric: str = 'f1'):
        """
        初始化参数优化器
        
        Args:
            multiplier_range: multiplier搜索范围
            window_range: window_len搜索范围
            optimization_metric: 优化目标指标
        """
        self.multiplier_range = multiplier_range
        self.window_range = window_range
        self.optimization_metric = optimization_metric
        
        self.optimization_results = []
        self.best_params = {}
        
    def grid_search(self, 
                    data: np.ndarray, 
                    labels: np.ndarray,
                    multiplier_step: float = 0.2,
                    window_step: int = 10,
                    cv_folds: int = 3) -> Dict:
        """
        网格搜索优化参数
        
        Args:
            data: 时间序列数据
            labels: 异常标签
            multiplier_step: multiplier步长
            window_step: window_len步长
            cv_folds: 交叉验证折数
            
        Returns:
            优化结果字典
        """
        print("开始网格搜索参数优化...")
        
        # 生成参数网格
        multipliers = np.arange(
            self.multiplier_range[0], 
            self.multiplier_range[1] + multiplier_step, 
            multiplier_step
        )
        windows = np.arange(
            self.window_range[0], 
            self.window_range[1] + window_step, 
            window_step
        )
        
        results = []
        best_score = -1
        best_params = {}
        
        # 时间序列交叉验证
        tscv = TimeSeriesSplit(n_splits=cv_folds)
        
        total_combinations = len(multipliers) * len(windows)
        current_combination = 0
        
        for multiplier in multipliers:
            for window_len in windows:
                window_len = int(window_len)
                current_combination += 1
                
                if current_combination % 10 == 0:
                    print(f"进度: {current_combination}/{total_combinations}")
                
                # 交叉验证
                cv_scores = []
                for train_idx, test_idx in tscv.split(data):
                    train_data, test_data = data[train_idx], data[test_idx]
                    train_labels, test_labels = labels[train_idx], labels[test_idx]
                    
                    # 训练检测器
                    detector = ThreeSigmaDetector(
                        window_len=window_len,
                        multiplier=multiplier
                    )
                    
                    # 流式检测
                    predictions = []
                    for x in test_data:
                        detector.fit(np.array([x]))
                        pred = detector.predict(np.array([x]))
                        predictions.append(pred)
                    
                    # 计算指标
                    if len(set(predictions)) > 1:
                        score = self._calculate_metric(test_labels, predictions)
                        cv_scores.append(score)
                
                if cv_scores:
                    avg_score = np.mean(cv_scores)
                    std_score = np.std(cv_scores)
                    
                    results.append({
                        'multiplier': multiplier,
                        'window_len': window_len,
                        'score': avg_score,
                        'score_std': std_score
                    })
                    
                    if avg_score > best_score:
                        best_score = avg_score
                        best_params = {
                            'multiplier': multiplier,
                            'window_len': window_len,
                            'score': avg_score
                        }
        
        self.optimization_results = results
        self.best_params = best_params
        
        print(f"网格搜索完成！最佳参数: {best_params}")
        return {
            'best_params': best_params,
            'all_results': results,
            'optimization_metric': self.optimization_metric
        }
    
    def bayesian_optimization(self, 
                             data: np.ndarray, 
                             labels: np.ndarray,
                             n_iterations: int = 50) -> Dict:
        """
        贝叶斯优化参数（简化版本）
        
        Args:
            data: 时间序列数据
            labels: 异常标签
            n_iterations: 迭代次数
            
        Returns:
            优化结果字典
        """
        print("开始贝叶斯优化参数...")
        
        # 简化版贝叶斯优化 - 随机搜索+早停
        results = []
        best_score = -1
        best_params = {}
        
        for i in range(n_iterations):
            # 随机采样参数
            multiplier = np.random.uniform(*self.multiplier_range)
            window_len = int(np.random.uniform(*self.window_range))
            
            # 评估参数
            detector = ThreeSigmaDetector(
                window_len=window_len,
                multiplier=multiplier
            )
            
            predictions = []
            for x in data:
                detector.fit(np.array([x]))
                pred = detector.predict(np.array([x]))
                predictions.append(pred)
            
            if len(set(predictions)) > 1:
                score = self._calculate_metric(labels, predictions)
                
                results.append({
                    'multiplier': multiplier,
                    'window_len': window_len,
                    'score': score
                })
                
                if score > best_score:
                    best_score = score
                    best_params = {
                        'multiplier': multiplier,
                        'window_len': window_len,
                        'score': score
                    }
            
            if (i + 1) % 10 == 0:
                print(f"贝叶斯优化进度: {i+1}/{n_iterations}")
        
        print(f"贝叶斯优化完成！最佳参数: {best_params}")
        return {
            'best_params': best_params,
            'all_results': results,
            'optimization_metric': self.optimization_metric
        }
    
    def sensitivity_analysis(self, 
                           data: np.ndarray, 
                           labels: np.ndarray,
                           fixed_param: str = 'multiplier',
                           fixed_value: float = 3.0) -> Dict:
        """
        参数敏感性分析
        
        Args:
            data: 时间序列数据
            labels: 异常标签
            fixed_param: 固定的参数 ('multiplier' 或 'window_len')
            fixed_value: 固定参数的值
            
        Returns:
            敏感性分析结果
        """
        print(f"开始参数敏感性分析 (固定{fixed_param}={fixed_value})...")
        
        results = []
        
        if fixed_param == 'multiplier':
            # 固定multiplier，变化window_len
            windows = np.arange(
                self.window_range[0], 
                self.window_range[1] + 10, 
                10
            )
            
            for window_len in windows:
                window_len = int(window_len)
                detector = ThreeSigmaDetector(
                    window_len=window_len,
                    multiplier=fixed_value
                )
                
                predictions = []
                for x in data:
                    detector.fit(np.array([x]))
                    pred = detector.predict(np.array([x]))
                    predictions.append(pred)
                
                if len(set(predictions)) > 1:
                    score = self._calculate_metric(labels, predictions)
                    results.append({
                        'window_len': window_len,
                        'multiplier': fixed_value,
                        'score': score
                    })
        
        else:  # fixed_param == 'window_len'
            # 固定window_len，变化multiplier
            multipliers = np.arange(
                self.multiplier_range[0], 
                self.multiplier_range[1] + 0.2, 
                0.2
            )
            
            for multiplier in multipliers:
                detector = ThreeSigmaDetector(
                    window_len=int(fixed_value),
                    multiplier=multiplier
                )
                
                predictions = []
                for x in data:
                    detector.fit(np.array([x]))
                    pred = detector.predict(np.array([x]))
                    predictions.append(pred)
                
                if len(set(predictions)) > 1:
                    score = self._calculate_metric(labels, predictions)
                    results.append({
                        'window_len': int(fixed_value),
                        'multiplier': multiplier,
                        'score': score
                    })
        
        print("参数敏感性分析完成！")
        return {
            'results': results,
            'fixed_param': fixed_param,
            'fixed_value': fixed_value
        }
    
    def compare_algorithms(self, 
                          data: np.ndarray, 
                          labels: np.ndarray) -> Dict:
        """
        对比算法性能
        
        Args:
            data: 时间序列数据
            labels: 异常标签
            
        Returns:
            对比结果
        """
        print("开始算法性能对比...")
        
        results = {}
        
        # 1. 固定参数的3-Sigma
        fixed_detector = ThreeSigmaDetector(window_len=50, multiplier=3.0)
        fixed_predictions = []
        for x in data:
            fixed_detector.fit(np.array([x]))
            pred = fixed_detector.predict(np.array([x]))
            fixed_predictions.append(pred)
        
        results['Fixed_3Sigma'] = self._calculate_all_metrics(labels, fixed_predictions)
        
        # 2. 优化参数的3-Sigma
        if self.best_params:
            optimized_detector = ThreeSigmaDetector(
                window_len=self.best_params['window_len'],
                multiplier=self.best_params['multiplier']
            )
            optimized_predictions = []
            for x in data:
                optimized_detector.fit(np.array([x]))
                pred = optimized_detector.predict(np.array([x]))
                optimized_predictions.append(pred)
            
            results['Optimized_3Sigma'] = self._calculate_all_metrics(labels, optimized_predictions)
        
        # 3. 自适应3-Sigma
        adaptive_detector = AdaptiveThreeSigmaDetector(auto_optimize=True)
        adaptive_predictions = []
        for i, x in enumerate(data):
            label = labels[i] if i < len(labels) else None
            adaptive_detector.fit(np.array([x]), label=label)
            pred = adaptive_detector.predict(np.array([x]))
            adaptive_predictions.append(pred)
        
        results['Adaptive_3Sigma'] = self._calculate_all_metrics(labels, adaptive_predictions)
        
        print("算法性能对比完成！")
        return results
    
    def _calculate_metric(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """计算指定的评估指标"""
        if self.optimization_metric == 'f1':
            return f1_score(y_true, y_pred, zero_division=0)
        elif self.optimization_metric == 'precision':
            return precision_score(y_true, y_pred, zero_division=0)
        elif self.optimization_metric == 'recall':
            return recall_score(y_true, y_pred, zero_division=0)
        else:
            return f1_score(y_true, y_pred, zero_division=0)
    
    def _calculate_all_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
        """计算所有评估指标"""
        return {
            'precision': precision_score(y_true, y_pred, zero_division=0),
            'recall': recall_score(y_true, y_pred, zero_division=0),
            'f1': f1_score(y_true, y_pred, zero_division=0),
            'accuracy': np.mean(y_true == y_pred)
        }
    
    def plot_optimization_results(self, save_path: Optional[str] = None):
        """绘制优化结果"""
        if not self.optimization_results:
            print("没有优化结果可绘制")
            return
        
        df = pd.DataFrame(self.optimization_results)
        
        # 创建热力图数据
        pivot_table = df.pivot_table(
            values='score', 
            index='multiplier', 
            columns='window_len', 
            aggfunc='mean'
        )
        
        plt.figure(figsize=(12, 8))
        sns.heatmap(
            pivot_table, 
            annot=True, 
            fmt='.3f', 
            cmap='viridis',
            cbar_kws={'label': f'{self.optimization_metric.upper()} Score'}
        )
        plt.title('3-Sigma Parameter Optimization Heatmap')
        plt.xlabel('Window Length')
        plt.ylabel('Multiplier')
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_sensitivity_analysis(self, 
                                sensitivity_results: Dict,
                                save_path: Optional[str] = None):
        """绘制敏感性分析结果"""
        results = sensitivity_results['results']
        fixed_param = sensitivity_results['fixed_param']
        
        df = pd.DataFrame(results)
        
        plt.figure(figsize=(10, 6))
        
        if fixed_param == 'multiplier':
            plt.plot(df['window_len'], df['score'], 'bo-', linewidth=2, markersize=6)
            plt.xlabel('Window Length')
            plt.title(f'Window Length Sensitivity Analysis (Fixed Multiplier={sensitivity_results["fixed_value"]})')
        else:
            plt.plot(df['multiplier'], df['score'], 'ro-', linewidth=2, markersize=6)
            plt.xlabel('Multiplier')
            plt.title(f'Multiplier Sensitivity Analysis (Fixed Window Length={sensitivity_results["fixed_value"]})')
        
        plt.ylabel(f'{self.optimization_metric.upper()} Score')
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.show()
    
    def plot_algorithm_comparison(self, 
                                comparison_results: Dict,
                                save_path: Optional[str] = None):
        """绘制算法对比结果"""
        algorithms = list(comparison_results.keys())
        metrics = ['precision', 'recall', 'f1', 'accuracy']
        
        # 准备数据
        data_matrix = []
        for metric in metrics:
            row = [comparison_results[alg][metric] for alg in algorithms]
            data_matrix.append(row)
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # 柱状图
        x = np.arange(len(metrics))
        width = 0.25
        
        for i, alg in enumerate(algorithms):
            values = [comparison_results[alg][metric] for metric in metrics]
            ax1.bar(x + i * width, values, width, label=alg)
        
        ax1.set_xlabel('Evaluation Metrics')
        ax1.set_ylabel('Score')
        ax1.set_title('Algorithm Performance Comparison - Bar Chart')
        ax1.set_xticks(x + width)
        ax1.set_xticklabels(metrics)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 雷达图
        angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False)
        angles = np.concatenate((angles, [angles[0]]))
        
        for alg in algorithms:
            values = [comparison_results[alg][metric] for metric in metrics]
            values = np.concatenate((values, [values[0]]))
            ax2.plot(angles, values, 'o-', linewidth=2, label=alg)
            ax2.fill(angles, values, alpha=0.25)
        
        ax2.set_xticks(angles[:-1])
        ax2.set_xticklabels(metrics)
        ax2.set_ylim(0, 1)
        ax2.set_title('Algorithm Performance Comparison - Radar Chart')
        ax2.legend()
        ax2.grid(True)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        plt.show()
    
    def generate_report(self, 
                       data: np.ndarray, 
                       labels: np.ndarray,
                       output_file: str = 'parameter_optimization_report.txt'):
        """生成优化报告"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("3-Sigma参数优化报告\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"数据集信息:\n")
            f.write(f"- 数据点数量: {len(data)}\n")
            f.write(f"- 异常点数量: {np.sum(labels)}\n")
            f.write(f"- 异常比例: {np.sum(labels)/len(labels):.3f}\n\n")
            
            if self.best_params:
                f.write(f"最佳参数:\n")
                f.write(f"- Multiplier: {self.best_params['multiplier']:.2f}\n")
                f.write(f"- Window Length: {self.best_params['window_len']}\n")
                f.write(f"- {self.optimization_metric.upper()} Score: {self.best_params['score']:.4f}\n\n")
            
            # 对比结果
            comparison_results = self.compare_algorithms(data, labels)
            f.write("算法性能对比:\n")
            for alg, metrics in comparison_results.items():
                f.write(f"\n{alg}:\n")
                for metric, value in metrics.items():
                    f.write(f"  - {metric}: {value:.4f}\n")
        
        print(f"优化报告已保存到: {output_file}") 