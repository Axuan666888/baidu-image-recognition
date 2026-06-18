# 图片智能识别后台管理系统

基于 Flask + 百度AI 开放平台的图片管理系统。

## 快速启动

### 方法一：双击运行
双击 `start.bat` 即可启动，浏览器访问 http://localhost:5000

### 方法二：手动运行
```bash
pip install -r requirements.txt
python app.py
```

## 配置百度AI

打开 `app.py`，找到以下位置修改：

```python
BAIDU_API_KEY = 'your_api_key_here'      # 替换为你的 API Key
BAIDU_SECRET_KEY = 'your_secret_key_here'  # 替换为你的 Secret Key
```

### 获取 API Key

1. 访问 https://console.bce.baidu.com/
2. 创建应用，选择「图像识别」服务
3. 复制 API Key 和 Secret Key

## 功能列表

- 图片上传（支持拖拽、多选）
- 5种识别类型：通用识别、植物、动物、菜品、Logo
- 识别结果可视化（标签云 + 置信度条形图）
- 图片搜索（按名称、标签、识别内容）
- 状态过滤（待识别/已识别/失败）
- 图片备注和标签管理
- 网格/列表两种视图

## 支持图片格式

JPG · PNG · GIF · BMP · WebP（最大 20MB）
