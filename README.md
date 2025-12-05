# cixGUI 二改版

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


## 许可证
本项目基于原项目的 GPL3.0 协议进行二次开发，遵循相同许可证条款。详情请参阅 [LICENSE](LICENSE) 文件。

>[!NOTE]注意
> 您可以自由复制、修改和分发本项目，但必须保留原作者信息及许可证声明，并确保衍生作品同样遵循 GPL3.0 协议。


## 致谢

- 特别感谢原项目作者 `pvzcxw` 开源 `cixGUI` 源码，为本改版提供了基础。

- 感谢 DeepSeek、ChatGPT、豆包等AI工具在开发过程中提供的辅助支持。

## 贡献
欢迎提交 Issue 或 Pull Request 参与项目改进。