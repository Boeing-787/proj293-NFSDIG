#!/bin/bash
readonly NUMOPS_SEVER=71
interval=20
output_dir="."  # 新增输出目录参数

# 解析命令行参数 -t
while getopts "t:o:" opt; do
  case $opt in
    t) interval=$OPTARG ;;
    o) output_dir=$OPTARG ;;
    \?) echo "无效选项: -$OPTARG" >&2; exit 1 ;;
  esac
done

# 如果指定了输出目录则创建目录
if [[ -n "$output_dir" ]]; then
  mkdir -p "$output_dir" || { echo "无法创建目录: $output_dir"; exit 1; }
fi

# 根据查看端确定操作数
count=${NUMOPS_SEVER}

get_data() {
  local output=$(nfsstat -s)
  ops=($(echo "$output" | grep -oP '\b(?=.*[a-zA-Z])[\w-]+\b'))
  values=($(echo "$output" | grep -oP '\b(?<!%)\d+\b(?!%)'))
  percentages=($(echo "$output" | grep -oE '[0-9]+%'))
}

# 定义函数：获取数组的最后N个元素
get_last_elements() {
    local arr=("${@:1:$#-1}")  
    local n="${@:$#}"         
    local len=${#arr[@]}
    local start=$(( len - n ))
    (( start < 0 )) && start=0
    echo "${arr[@]:$start}"
}

# 第一次数据采集
get_data
initial_values=($(get_last_elements "${values[@]}" "$NUMOPS_SEVER"))

echo "NFS初始数据采样完成，正在监控，请等待${interval}秒..."
sleep "$interval"


get_data
new_values=($(get_last_elements "${values[@]}" "$NUMOPS_SEVER"))

# 计算差值
delta_values=()
for ((i=0; i<NUMOPS_SEVER; i++)); do
  initial=${initial_values[$i]}
  new=${new_values[$i]}
  delta=$((new - initial))
  delta_values+=("$delta")
done

# 计算总请求数
total=0
for delta in "${delta_values[@]}"; do
  ((total += delta))
done

# 生成JSON文件（当total>0且指定了输出目录时）
if (( total > 0 )) && [[ -n "$output_dir" ]]; then
  timestamp=$(date +%Y%m%d-%H%M%S)
  json_file="${output_dir}/nfs_stats_${timestamp}.json"
  
  # 构建JSON内容
  json_content='{
  "interval": '$interval',
  "operations": {'
  
  for ((i=0; i<NUMOPS_SEVER; i++)); do
    op=${ops[$(( ${#ops[@]} - NUMOPS_SEVER + i ))]}
    delta=${delta_values[$i]}
    json_content+="\n    \"$op\": $delta"
    (( i < NUMOPS_SEVER-1 )) && json_content+=","
  done

  json_content+='
  }
}'
  
  echo -e "$json_content" > "$json_file"
  echo "数据已保存至: $json_file"
fi

# 生成统计报告
echo "------------------------------------------------"
if (( total == 0 )); then
  echo "无增量（采样间隔: ${interval}秒）"
else
  for ((i=0; i<NUMOPS_SEVER; i++)); do
    op=${ops[$(( ${#ops[@]} - NUMOPS_SEVER + i ))]}
    delta=${delta_values[$i]}
    percent=$(echo "scale=2; 100 * $delta / $total" | bc)
    printf "%-20s %-12d %.2f%%\n" "$op" "$delta" "$percent"
  done
fi
echo "================================================"
echo "总请求增量: $total (采样间隔: ${interval}秒)"
