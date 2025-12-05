# Cai Installer Gui

![](imgs/image.png)

本项目是基于 [pvzcxw/cixGUI](https://github.com/pvzcxw/cixGUI) 的二次开发版本。原项目因维护精力有限已停止更新，本改版旨在继续维护该工具，修复已知问题并增加新功能，为用户提供更稳定的使用体验。


## 原项目说明

原项目 `Cai Installer Gui` 是一款用于游戏安装相关的GUI工具，因原作者需专注于 `cixWeb UI` 开发，已于此前宣布停止对 `cixGUI` 的维护。原作者开放了全部源码（基于 GPL3.0 协议），鼓励社区继续开发迭代。

详情可参考原项目声明：[停更通知](https://github.com/pvzcxw/cixGUI)


## 二改版特性

- 继承原项目核心功能，保持与原版本的兼容性
- 添加 Walftech 清单库

## 安装与使用

### 环境要求

- Windows 10+
- Python 3.8+

### 安装步骤

1. 克隆本项目源码：
   ```shell
   git clone https://github.com/WingChunWong/cixGUI.git  
   
   cd cixGUI
   ```

2. 安装依赖：
   ```shell
   pip install -r requirements.txt
   ```

3. 运行程序：
   ```shell
   python frontend_gui.py
   ```

4. 获取Github Personal Token

具体步骤:
1. 登录 GitHub：在浏览器中打开 github.com 并登录你的账户。
2. 进入设置：点击页面右上角的个人资料照片，然后选择 Settings (设置)。
3. 找到开发者设置：在左侧边栏中，找到并点击 Developer settings (开发者设置)。
4. 选择 Classic Tokens：在左侧边栏的 "Personal access tokens" (个人访问令牌) 下，点击 Tokens (classic) (令牌(经典))。
5. 生成新令牌：点击 Generate new token (生成新令牌)，然后选择 Generate new token (classic) (生成新令牌(经典))。
6. 配置令牌信息：
   1. Note (备注)：给你的令牌起一个描述性的名字（例如 "My CLI Token"）。
   2. Expiration (到期时间)：选择令牌的过期时间（例如 30天, 90天或自定义）。
   3. Select scopes (选择范围)：根据需要勾选权限。如果你要从命令行访问仓库，至少需要勾选 `repo` 及其子项。
7. 生成并复制：点击 Generate token (生成令牌) 按钮。系统会立即显示你的令牌，立即复制这个字符串，因为你离开此页面后将无法再次看到明文。 

## 许可证
本项目基于原项目的 GPL3.0 协议进行二次开发，遵循相同许可证条款。详情请参阅 [LICENSE](LICENSE) 文件。

>[!NOTE]
> 您可以自由复制、修改和分发本项目，但必须保留原作者信息及许可证声明，并确保衍生作品同样遵循 GPL3.0 协议。


## 致谢

- 特别感谢原项目作者 `pvzcxw` 开源 `cixGUI` 源码，为本改版提供了基础。

- 感谢 DeepSeek、ChatGPT、豆包等AI工具在开发过程中提供的辅助支持。

## 贡献
欢迎提交 Issue 或 Pull Request 参与项目改进。
