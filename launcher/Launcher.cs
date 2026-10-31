// file: Launcher.cs
// description: 便携版启动器 —— 定位同目录下的 python\pythonw.exe 与 standalone.py 并启动批量导出插件界面
// author: IYATT-yx
// repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
// copyright:  Copyright (c) 2026 IYATT-yx.
//             Licensed under the MIT License. See LICENSE file in the project root for full license information.
//
// 编译（开发机，需 .NET Framework 自带的 csc）：
//   csc /nologo /target:winexe /platform:anycpu /win32icon:icon.ico /out:批量导出插件.exe launcher\Launcher.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class Program
{
    /// <summary>
    /// 启动入口：使用便携包自带的 Python 运行时打开插件界面
    /// </summary>
    [STAThread]
    private static void Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string pythonw = Path.Combine(root, "python", "pythonw.exe");
        string python = Path.Combine(root, "python", "python.exe");
        string script = Path.Combine(root, "standalone.py");

        if (!File.Exists(script))
        {
            ShowError("便携包文件不完整：缺少 standalone.py。\n请重新解压完整的压缩包。");
            return;
        }

        string interpreter = File.Exists(pythonw) ? pythonw : python;
        if (!File.Exists(interpreter))
        {
            ShowError("便携包文件不完整：缺少 python\\pythonw.exe。\n请重新解压完整的压缩包。");
            return;
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = interpreter;
            startInfo.Arguments = Quote(script) + BuildArguments(args);
            startInfo.WorkingDirectory = root;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            Process.Start(startInfo);
        }
        catch (Exception ex)
        {
            ShowError("启动失败：" + ex.Message);
        }
    }

    /// <summary>
    /// 拼接启动参数（支持 --cli 等原有命令行参数）
    /// </summary>
    private static string BuildArguments(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return string.Empty;
        }
        StringBuilder builder = new StringBuilder();
        foreach (string arg in args)
        {
            builder.Append(' ');
            builder.Append(Quote(arg));
        }
        return builder.ToString();
    }

    /// <summary>
    /// 命令行参数加引号
    /// </summary>
    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    /// <summary>
    /// 显示错误提示窗口
    /// </summary>
    private static void ShowError(string message)
    {
        MessageBox.Show(message, "批量导出插件", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
