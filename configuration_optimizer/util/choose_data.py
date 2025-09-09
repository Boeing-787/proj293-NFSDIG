import pandas as pd

# 原始训练集路径
train_csv = "../data/nfs_complete_data.csv"
# 修正后的训练集路径
new_train_csv = "../data/train_dataset/nfs_dataset_train.csv"
# 测试集输出路径
test_csv = "../data/test_dataset/nfs_dataset_test.csv"

# 读取完整数据
df = pd.read_csv(train_csv)

# 随机抽取200条作为测试集
test_df = df.sample(n=500, random_state=42)
# 从原数据中移除这些测试集样本（按索引删除）
train_df = df.drop(test_df.index)

# 保存
train_df.to_csv(new_train_csv, index=False)
test_df.to_csv(test_csv, index=False)

print(f"已从 {train_csv} 中抽取 500 条作为测试集，")
print(f"新训练集保存在 {new_train_csv}")
