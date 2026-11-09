# 电梯门开关检测服务 · ROS 2 Humble

用一张新的 RGB 图像判断眼前电梯门是否完全打开。服务常驻、模型启动时加载一次；每次空请求只推理 **1 frame**，该帧全开概率 **严格大于阈值** 返回 `100.0`，否则返回 `0.0`。没有一秒采样窗口、五帧采样、平均或投票。

本包沿用旧门检测的 ROS 包名、服务名、接口类型、相机 topic 和默认配置。使用独立的电梯门 YOLO26x 第 5 轮模型，不使用之前的玻璃门模型。机器人停靠位置、导航和下一个 waypoint 由调用方处理。

## 1. 接口与行为

| 项目 | 值 |
|---|---|
| ROS 包 | `door_opening_server` |
| 节点 | `door_opening_server` |
| 服务 | `/inspection/detection_door_opening` |
| 类型 | `scan_planner_msgs/srv/DetectDoorOpening` |
| 请求 | 空请求 |
| 响应 | `float32 opening_percent`，只返回 `0.0` 或 `100.0` |
| 默认图像 topic | `/camera/color/image_raw` |
| 输入 | `sensor_msgs/msg/Image`，RGB 彩色图像 |
| 状态诊断 | `/inspection/detection_door_opening/details`，`std_msgs/msg/String` 内含 JSON |

```srv
---
float32 opening_percent
```

**调用：**

```bash
ros2 service call /inspection/detection_door_opening \
  scan_planner_msgs/srv/DetectDoorOpening '{}'
```

每次调用的流程：

1. 创建新的单帧接收任务，不使用上一请求或请求前缓存的画面。
2. 接收第一张采集时间不早于请求开始、到达时未过期的图像。
3. 立即推理一次；`p(fully_open) > threshold` 返回 100，等于或低于阈值返回 0。
4. 没有有效新帧、图像格式错误、推理异常或非有限概率均返回 0。忙碌时的并发请求也直接返回 0，不排队。

`opening_percent` 是兼容旧接口的二值字段，**不是实际开门百分比，也不是概率**。返回 0 还可能表示本次检测失败，具体原因看诊断 topic / 日志。单帧判定没有连续帧一致性保障。

## 2. 下载模型

仓库代码不包含原始视频、标注、训练数据或大模型二进制。模型是版本固定的 GitHub Release 附件，下载清单在 `model_release.json`，部署元数据在 `src/door_opening_server/models/elevator_epoch5.json`。

```bash
git clone https://github.com/cicaburnwood-crypto/elevator-door-opening-service.git
cd elevator-door-opening-service
# 私有仓库需要当前账号具有访问权限：先 gh auth login，或设置 GH_TOKEN/GITHUB_TOKEN。
python3 tools/download_model.py
```

脚本只依赖 Python 标准库。它从 Release `v1.0.0` 下载 `elevator_epoch5.onnx`，验证 SHA256 后写入包内 `models/`。已有同哈希模型则跳过；遇到不同内容的已有文件会报错，不覆盖它。也可以手动从 Release 下载 ONNX 后放入同一目录。鉴权令牌不要写进 YAML、源码或命令行参数。

## 3. 安装与构建

目标：Ubuntu 22.04、ROS 2 Humble、Python 3.10。CPU 使用以下参考依赖；服务运行时只需要 ONNX Runtime、NumPy 和 Pillow，不需要 PyTorch、Ultralytics、Depth 或 VLM。

```bash
source /opt/ros/humble/setup.bash
python3 -m pip install --user -r requirements-cpu.txt

# 先 source 机器人已有 scan_planner_msgs 所在工作区：
source /path/to/scan_planner_ws/install/setup.bash

mkdir -p ~/door_ws/src
cp -r src/door_opening_server ~/door_ws/src/
cd ~/door_ws
colcon build --packages-select door_opening_server --symlink-install
source install/setup.bash
ros2 launch door_opening_server door_opening.launch.py
```

请先下载模型再构建，确保 ONNX 被安装到包的 share 目录。Python 依赖必须安装到运行 ROS 节点实际使用的 Python 环境；不要混用本机 Python 3.11 与 Humble 的 Python 3.10。

`scan_planner_msgs` 必须来自机器人的真实工程。接口参考在 `interfaces/DetectDoorOpening.srv`。若现有消息包缺少它，把该文件加入 `srv/`，并在现有 `rosidl_generate_interfaces(...)` 中追加 `"srv/DetectDoorOpening.srv"` 后构建。**不要用 tests 中的最小测试消息包覆盖机器人的消息包。**

本包与旧服务使用相同的包名、节点名和服务名。部署到独立工作区或备份替换旧包，运行时只启用其中一个服务端；不要同时启动两个同名服务。

## 4. 所有可调服务参数

服务参数在启动时读取，运行中为只读；修改 YAML 或启动参数后重启节点。默认 YAML：`src/door_opening_server/config/door_opening.yaml`。

| 参数 | 默认值 | 范围 / 可选值 | 作用及调整建议 |
|---|---|---|---|
| `image_topic` | `/camera/color/image_raw` | 非空 ROS topic | 改成机器人实际发布的 RGB topic。必须是原始 `Image`，不是 `CompressedImage`。 |
| `model_path` | 自动定位包内 `models/elevator_epoch5.onnx` | 本机 ONNX 文件路径 | 自定义模型旁必须有同名 `.json` 元数据；加载前校验 SHA256、类别顺序和输入输出格式。 |
| `provider` | `auto` | `auto` / `cpu` / `cuda` | auto 优先已安装的 CUDA provider，否则 CPU。cuda 明确要求 CUDA，缺失或回落时启动报错。 |
| `intra_op_threads` | `4` | 整数 ≥ 1 | ONNX Runtime CPU 算子线程数，inter-op 固定为 1。适当减少可避免与导航争抢 CPU；CUDA 路径也有部分 CPU 工作。 |
| `max_frame_age_sec` | `0.25` | `(0, 1]` 秒 | 图像到达时，ROS 当前时间减采集时间的上限。网络延迟大可适当增加，但允许的画面也更旧。未来时间戳不接受。 |
| `image_reliability` | `best_effort` | `best_effort` / `reliable` | 图像订阅 QoS。其余固定 KEEP_LAST、depth=1、VOLATILE。reliable 订阅端不能接收 best_effort 发布端。 |
| `threshold` | **`0.47`** | `(0, 1)` | 保留旧服务默认值，`p > threshold` 才返回 100。降低通常提高全开 Recall，也可能增加误报；提高通常相反。 |
| `frame_timeout_sec` | **`1.0`** | `(0, 30]` 秒 | **仅等待第一张有效新帧的最长时间**。帧一到就开始推理，不等满该时间。该值不限制后续 ONNX 推理耗时。 |

相机 `header.stamp` 必须非零，使用与节点一致的 ROS 时钟，并代表采集时间。支持 `rgb8`、`bgr8`、`rgba8`、`bgra8`，正确处理通道顺序和行填充。零时间戳、请求前的帧、未来时间戳、过期帧不会触发推理。收到第一张有效帧后不再换帧或追加帧。

**配置优先级：**节点默认值 < YAML < 显式 launch 参数。服务 launch 的覆盖参数默认留空，未指定时不会覆盖 YAML。

```bash
# 沿用全部默认参数
ros2 launch door_opening_server door_opening.launch.py

# 常用修改：相机 topic、CUDA、模型验证时使用的 0.5 阈值
ros2 launch door_opening_server door_opening.launch.py \
  image_topic:=/camera/camera/color/image_raw provider:=cuda threshold:=0.5

# 低帧率相机：最多等 2 秒，但新帧到达后立即推理
ros2 launch door_opening_server door_opening.launch.py \
  frame_timeout_sec:=2.0 max_frame_age_sec:=0.3 image_reliability:=reliable

# 整份自定义 YAML（顶层节点名仍为 door_opening_server）
ros2 launch door_opening_server door_opening.launch.py params_file:=/absolute/path/elevator.yaml

# 不用 launch，直接启动节点；ROS 标准 --params-file 和 -p 同样适用
ros2 run door_opening_server detection_door_opening_server --ros-args \
  -p threshold:=0.5 -p provider:=cpu -p intra_op_threads:=2
```

`use_sim_time` 是 ROS 标准参数（默认 false）；回放仿真数据时可在 YAML 中设置，并确保 `/clock` 正常发布。跨机器通信还需正确设置 `ROS_DOMAIN_ID`、DDS 网络和时钟同步。服务名固定为上文默认名称；如用 ROS remap 改名，调用方与诊断 topic 配置也要相应调整。

## 5. GPU / AGX Thor

CPU 依赖文件用于参考运行，不要在已有 GPU ONNX Runtime 环境上同时安装 `onnxruntime` CPU wheel。AGX Thor 需要适配其 ARM64、JetPack/CUDA/cuDNN 的 NVIDIA ONNX Runtime 构建；不要复制开发本的 x86 wheel。`provider:=cuda` 使用 ONNX Runtime CUDA，不是 TensorRT engine。

```bash
python3 -c 'import onnxruntime as ort; print(ort.get_available_providers())'
ros2 launch door_opening_server door_opening.launch.py provider:=cuda
```

节点启动时加载模型并预热后才提供服务。没有对 Thor 实机进行延时或显存测试。服务总耗时为等待一帧的时间 + 图像转换 + 单次推理 + ROS 通信，并不是固定 1 秒。

## 6. 可选 GUI 与 USB 相机

```bash
ros2 launch door_opening_server door_opening_gui.launch.py
# http://127.0.0.1:8878/
```

GUI 的“检测一次”调用真实 ROS 服务，显示该单帧的全开概率及 0/100 结果；实时预览不持续跑推理。GUI launch 支持上述服务参数中的 `image_topic/provider/model_path/threshold/frame_timeout_sec/max_frame_age_sec/intra_op_threads/image_reliability`，另有：

| GUI 参数 | 默认值 | 说明 |
|---|---|---|
| `gui_host` | `127.0.0.1` | 保持本机访问；远程查看建议 SSH 转发。GUI 没有用户鉴权，不应直接暴露到公网。 |
| `gui_port` | `8878` | HTTP 监听端口。 |

GUI 继承旧客户端 20 秒请求超时；若把采帧超时调到接近或超过 20 秒，请使用 ROS 客户端调用并设置更长的客户端等待时间。

GUI launch 使用上述显式默认值，不提供 `params_file`；需要自定义 YAML 时，分别启动服务 launch 和 `ros2 run door_opening_server door_opening_gui`。

已有 USB 桥接工具保留在 `tools/usb_camera_bridge.py`（需要 FFmpeg 和 Pillow）。它通过 GUI 发布 RGB，使用时先启动 GUI；相机设备号以实际枚举为准。机器人已有相机驱动时无需该工具。

## 7. 常驻与开机启动

前台 launch 本身就是常驻服务，可以重复调用。后台随系统启动可使用 `deploy/elevator-door.service` 模板：先修改用户名、HOME、DOOR_WS、ExecStart，再安装。

```bash
sudo cp deploy/elevator-door.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now elevator-door.service
journalctl -u elevator-door.service -f
```

`tools/run_service.sh` 默认加载 `~/door_ws/install/setup.bash`，可通过 `DOOR_WS` 环境变量改变。构建该工作区前应加载真实的消息包工作区，保证安装环境保留依赖链。systemd 模板中的 ROS_DOMAIN_ID 必须与相机和调用方一致。该模板不会启动相机驱动，也不会自动启动导航。

## 8. 查看概率与排错

```bash
ros2 service type /inspection/detection_door_opening
ros2 topic info /camera/color/image_raw -v
ros2 topic echo /inspection/detection_door_opening/details std_msgs/msg/String
ros2 param get /door_opening_server threshold
```

诊断 JSON 保留旧 GUI 使用的字段：`probabilities`（空或一个值）、`sample_count`（0 或 1）、`mean_probability`（为了兼容保留，成功时等于唯一概率）、`threshold`、`opening_percent`、`started_ns`、`duration_s`、`reason`、成功时的 `stamp_ns`。规则字段为 `single_frame_gt_threshold`。忙碌时被拒绝的并发请求只返回 0 并记录日志，不发布可能与当前请求混淆的诊断消息。

| 现象 | 检查内容 |
|---|---|
| 一直返回 0，reason 为 `no_fresh_frame_before_timeout` | 相机是否连续发布、topic/QoS 是否匹配、时间戳是否非零且时钟一致、图像年龄是否超限。 |
| `inference_error` | 图像 encoding/stride、模型输入输出、ONNX Runtime 日志。 |
| 启动时缺少模型 | 先下载 Release 附件，再重新构建或检查 `model_path`。 |
| 模型 SHA256 不匹配 | 文件是否下载完整；不要编辑哈希来掩盖损坏，应重新下载正确版本。 |
| 找不到 `scan_planner_msgs` | source 正确工作区，确认服务类型拼写是 **DetectDoorOpening**。 |
| 返回 100 但画面不符合预期 | 查看单帧概率、相机视角是否与训练数据一致，必要时调高阈值并用新数据验证。 |

## 9. 模型结果与测试

模型来自独立电梯门数据：TR1–TR19 共 13,283 帧训练；VAL-1、VAL-2 共 1,177 帧验证。第 12 轮早停，按偏重 Recall 的 F2 选中第 5 轮。未混入旧玻璃门数据。标签平滑 0.05，人工标签不修改。

在**验证阈值 0.5** 下：Accuracy 96.35%，全开 Recall 100%，Precision 86.13%，43 帧误报、0 帧漏报。VAL 参与了模型选择，属于验证结果，不是独立测试。**本服务为保留旧默认值使用阈值 0.47，上述统计不能直接当作 0.47 的性能报告。** 设 `threshold:=0.5` 可使用验证时的阈值；此服务采用严格 `>`，旧离线视频脚本采用 `>=`，恰好等于阈值时边界行为不同。

测试分为：单帧时序策略、真实 Humble DDS 空请求与图像发布、实际 ONNX 模型加载、原 PyTorch 与 ONNX 的概率等价。2026-11-09 在 Ubuntu 22.04 / Humble / Python 3.10 容器中通过 19 项测试（18 项策略与 ROS 通信、1 项安装后 launch）。16 个预选验证帧的 ONNX/PyTorch 概率最大差异为 1.252e-6，0.47 阈值下判定全部一致。结果摘要在 `test_results/`，不上传训练图像。

```bash
# 先下载模型；测试镜像自动生成隔离测试用消息包
docker build -f Dockerfile.test -t elevator-door:humble-test .
docker run --rm --network none elevator-door:humble-test
```

模型基于 [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26/)。第三方模型和运行库的许可分别由其上游提供，本仓库不替代这些条款。
