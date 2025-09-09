import numpy as np
import random
from typing import Optional, List, Tuple

def localized_sample(x: np.array, m, score, scale=2, rho=None, sigma=1 / 12, random_state=None):
# def localized_sample(x: np.ndarray,
#                      m: int,
#                      score: np.ndarray,
#                      scale: int = 2,
#                      rho: Optional[float] = None,
#                      sigma: float = 1 / 12,
#                      random_state: Optional[int] = None) -> Tuple[np.ndarray, List[int]]:
    """
    根据采样得分score_func函数对x进行随机局部化采样
    :param x:采样点的原数据矩阵, shape=(n,k), n是数据个数, k是kpi种数
    :param m:采样数量
    :param score: 每个采样点的采样得分, 得分越高, 越容易采样到该点的信息
    :param rho: 采样单元中心点被采样概率, 若为None, 取1/(sqrt(2pi)*sigma)
    :param scale: 将原采样点数扩充至原来的scale倍
    :param sigma: 高斯随机采样标准差
    :param random_state: 随机数种子
    :return:采样矩阵 shape=(m,n), 每个采样单元的所在时间序列位置列表
    """

    n = x.shape[0]
    t = np.zeros(n + 1)
    t[0] = 0
    for i in range(n):
        t[i + 1] = t[i] + score[i]
    t = t / t[n]
    # t 表示每个采样点的累积概率
    # t = np.cumsum(score) / np.sum(score)

    if random_state:
        random.seed(random_state)
        np.random.seed(random_state)

    sample_mat = np.zeros((m, n))
    su_center = []
    # 从n个时间点里面随机选m个时间点作为采样单元的中心
    su_timestamp = np.random.choice(range(n), m, replace=False)

    for i in range(m):
        c = su_timestamp[i]
        # 采样单元中心点对应的累计概率
        su_center.append(t[c])
        # 将采样单元所属区间的采样中心位置的权重先置为1, 防止该单元什么都不采样
        sample_mat[i][c] = 1

    step = each_step = 1 / (scale * n)
    if rho is None:
        rho = 1 / (np.sqrt(2 * np.pi) * sigma)

    y = 1
    while step > t[y]:
        y += 1

    # 计算当前步长与采样单元中心点之间的距离，并基于高斯分布计算采样概率。
    while step <= 1:
        for j in range(m):
            c = su_center[j]
            if np.abs(c - step) > 3 * sigma:
                continue
            p = rho * np.exp(np.square((c - step) / sigma) / -2)
            if random.random() < p:
                sample_mat[j][y - 1] += 1
        step += each_step
        while step > t[y] and y < n:
            y += 1

            
    for row in range(m):
        # 权重归一化
        sample_mat[row] /= np.sum(sample_mat[row])
    sample_mat = np.mat(sample_mat)
    # 最后返回一个m*n的矩阵, 每一行代表一个采样单元, 该行的每个元素代表该采样单元在对应时间序列位置的采样概率
    return sample_mat, su_timestamp
