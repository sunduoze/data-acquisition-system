import sys
import socket
import subprocess
from PyQt5 import sip
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton, QLabel, \
    QHBoxLayout, QLineEdit, QScrollArea
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QTimer, QDateTime
import pyqtgraph as pg
import numpy as np
from dash import Dash, dcc, html, dash_table
import webbrowser
import time


class DataReceiver(QObject):
    data_received = pyqtSignal(list)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.data_buffer = []
        self.csv_file = None
        self.start_time = None

    def start_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.running = True
        self.data_buffer = []

        while self.running:
            client_socket, address = self.server_socket.accept()
            with client_socket:
                print('Connected by', address)
                buffer = ""
                while self.running:
                    data = client_socket.recv(1024).decode('utf-8')
                    if not data:
                        break

                    buffer += data
                    messages = buffer.split('\r\n')

                    for msg in messages[:-1]:
                        data_values = [float(value) for value in msg.split(',')]
                        self.data_received.emit(data_values)
                        self.data_buffer.append(data_values)

                        if self.csv_file is not None:
                            timestamp = (QDateTime.currentMSecsSinceEpoch() - self.start_time) / 1000.0
                            row = [f'{timestamp:.3f}'] + list(map(str, data_values))
                            self.csv_file.write(','.join(row) + '\n')

                    buffer = messages[-1]

    def stop_server(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None

    def start_csv_file(self):
        timestamp = QDateTime.currentDateTime().toString("yyyyMMddhhmmss")
        filename = f"DAS_{timestamp}.csv"
        self.csv_file = open(filename, 'w')
        self.csv_file.write("Timestamp,CH1,CH2,CH3,CH4,CH5,CH6,CH7,CH8\n")
        self.start_time = QDateTime.currentMSecsSinceEpoch()


class PlotUpdater(QObject):
    update_plot_signal = pyqtSignal(list)
    update_text_signal = pyqtSignal(str)

    def __init__(self, curve_dict, text_edit):
        super().__init__()
        self.curve_dict = curve_dict
        self.text_edit = text_edit

    def update_plot(self, data_values):
        self.update_plot_signal.emit(data_values)

    def update_text(self, text):
        self.update_text_signal.emit(text)


class SpectrumAnalysisThread(QThread):
    def run(self):
        try:
            subprocess.run(['python', 'spectrum_analysis.py'], timeout=60 * 1)  # Run for 1 minute (60 seconds)
        except subprocess.TimeoutExpired:
            print("Spectrum Analysis completed.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.run_dash_flag = 0

        self.setWindowTitle('Data Acquisition System              by sunduoze 20231231')
        self.setFixedSize(1800, 1500)

        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)
        # 禁止拖动图表，并启用抗锯齿
        pg.setConfigOptions(background='k', foreground='y', leftButtonPan=False, antialias=False, useOpenGL=True,
                            useNumba=True)

        # 创建水平布局
        self.input_layout = QHBoxLayout()

        # 创建 IP 和端口输入框
        self.ip_port_input = QLineEdit(self)
        self.ip_port_input.setText("192.168.1.1:1234")
        self.input_layout.addWidget(self.ip_port_input)

        # 创建按钮
        self.start_button = QPushButton('Start', self)
        self.stop_button = QPushButton('Stop', self)
        self.clear_chart_button = QPushButton('Clear Chart', self)
        self.clear_data_button = QPushButton('Clear Data', self)

        # 将按钮添加到布局中
        self.input_layout.addWidget(self.start_button)
        self.input_layout.addWidget(self.stop_button)
        self.input_layout.addWidget(self.clear_chart_button)
        self.input_layout.addWidget(self.clear_data_button)

        # 将输入布局添加到主布局
        self.layout.addLayout(self.input_layout)

        # 创建图表布局
        self.plot_layout = QVBoxLayout()

        self.plot_widget = pg.PlotWidget()
        self.plot_layout.addWidget(self.plot_widget)

        self.plot_widget.setXRange(-200, 2000)  # 设置y轴范围
        self.plot_widget.showGrid(x=True, y=True)

        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.text_edit = QTextEdit()
        self.scroll_area.setWidget(self.text_edit)
        self.text_edit.setFixedWidth(1760)
        self.text_edit.setFixedHeight(500)

        self.scrollBar = self.scroll_area.verticalScrollBar()

        self.scrollBar.setValue(25)

        # 将滚动区域添加到图表布局
        self.plot_layout.addWidget(self.scroll_area)

        # 将图表布局添加到主布局
        self.layout.addLayout(self.plot_layout)

        # 创建一个水平布局
        self.labels_layout = QHBoxLayout()

        # 创建两个 QLabel 控件
        self.label1 = QLabel(self)
        self.label1.setText("Label 1")
        self.labels_layout.addWidget(self.label1)
        self.original_font = self.label1.font()  # 保存 label 的原始字体
        new_font = self.label1.font()
        new_font.setBold(True)
        new_font.setPointSize(new_font.pointSize() + 6)
        self.label1.setFont(new_font)

        self.label2 = QLabel(self)
        self.label2.setText("Label 2")
        self.labels_layout.addWidget(self.label2)
        new_font = self.label2.font()
        new_font.setBold(True)
        new_font.setPointSize(new_font.pointSize() + 6)
        self.label2.setFont(new_font)

        # 将 labels_layout 添加到主布局中
        self.layout.addLayout(self.labels_layout)

        # 创建曲线图
        self.curve_dict = {}
        self.curve_data = {}
        colors = ['#e6194B', '#3cb44b', '#ffe119', '#4363d8', '#f58231', '#911eb4', '#42d4f4', '#f032e6']
        channel_name = ['TCD', 'TCD_PS', 'AUX_VOLT', 'PID', 'DID', 'PID_PS', 'VBUS', 'AUX_CURR']
        widths = [3, 3, 3, 3, 3, 3, 3, 3]

        # 添加图例
        self.plot_widget.addLegend(labelTextColor="black", offset=(2, 2), labelTextSize='12pt',
                                   brush=pg.mkBrush(color='#E8f0f0'))

        for i in range(8):
            name = channel_name[i % len(channel_name)]
            pen = pg.mkPen(cosmetic=True, color=colors[i % len(colors)], width=widths[i % len(widths)])
            self.curve_dict[i] = self.plot_widget.plot(pen=pen, name=name, labelTextSize='16pt')
            self.curve_data[i] = np.array([])

        self.data_receiver = DataReceiver('', 0)
        self.plot_updater = PlotUpdater(self.curve_dict, self.text_edit)

        self.data_receiver.data_received.connect(self.plot_updater.update_plot)
        self.plot_updater.update_plot_signal.connect(self.update_plot)
        self.plot_updater.update_text_signal.connect(self.update_text)

        self.data_thread = QThread()
        self.plot_thread = QThread()
        self.start_dash_thread = QThread()
        self.open_broswer_thread = QThread()

        self.data_receiver.moveToThread(self.data_thread)
        self.plot_updater.moveToThread(self.plot_thread)

        self.data_thread.started.connect(self.data_receiver.start_server)
        self.plot_thread.started.connect(self.start_plotting)
        self.start_dash_thread.started.connect(self.run_dash)
        self.open_broswer_thread.started.connect(self.open_broswer)

        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.clicked.connect(self.run_dash)
        self.stop_button.clicked.connect(self.open_broswer)

        self.clear_chart_button.clicked.connect(self.clear_chart)
        self.clear_data_button.clicked.connect(self.clear_data)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(100)  # 设置定时器，每100毫秒更新一次绘图

    def start_plotting(self):
        for i in range(8):
            self.curve_dict[i].setDownsampling(auto=True, method='peak')
            self.curve_dict[i].setClipToView(True)

    def start_server(self):
        if not self.data_thread.isRunning():
            ip, port = self.ip_port_input.text().split(':')
            self.data_receiver.host = ip
            self.data_receiver.port = int(port)
            self.data_receiver.start_csv_file()
            self.data_thread.start()
            self.start_button.setStyleSheet("background-color: green")
            self.start_button.setEnabled(False)

    def stop_server(self):
        if self.data_thread.isRunning():
            self.data_receiver.stop_server()
            self.data_thread.quit()
            self.data_thread.wait()
            self.start_button.setStyleSheet("")
            self.start_button.setEnabled(True)


    def run_dash(self):
        print("run dash")
        # Start spectrum analysis in a separate thread
        app = sepctrum_analysis()
        app.run_server(debug=True, threaded=True)

    def open_broswer(self):
        # 等待应用启动完成，可以根据实际情况调整等待时间
        time.sleep(5)
        print("open broswer")
        # 你的Dash应用启动的URL
        url = "http://127.0.0.1:8050/"
        webbrowser.open(url, new=2)

    def clear_chart(self):
        for i in range(8):
            self.curve_data[i] = np.array([])
            self.curve_dict[i].setData(y=self.curve_data[i])

    def clear_data(self):
        self.text_edit.clear()

    def update_plot(self, data_values=None):
        try:
            if data_values is not None:
                if not isinstance(data_values, list) or len(data_values) != 8:
                    raise ValueError("Invalid data format")

                for i, value in enumerate(data_values):
                    if i >= 8:
                        break
                    if not isinstance(value, (int, float)):
                        raise ValueError(f"Invalid data type for value {i}: {type(value)}")

                    if len(self.curve_data[i]) >= 20000:
                        self.curve_data[i] = np.roll(self.curve_data[i], -1)
                        self.curve_data[i][-1] = value
                    else:
                        self.curve_data[i] = np.append(self.curve_data[i], value)

                    self.curve_dict[i].setData(y=self.curve_data[i])
                    self.label1.setText("VOLT:" + str(data_values[2]) + "V")
                    self.label2.setText("CURR:" + str(data_values[7]) + "A")

                # 滚动显示最新40行文本数据
                current_text = self.text_edit.toPlainText()
                new_text = '\n'.join([current_text] + [', '.join(map(str, data_values))])
                self.text_edit.setPlainText('\n'.join(new_text.splitlines()[-40:]))
                # self.scroll_area.verticalScrollBar().setValue(30)
                self.scrollBar.setValue(30)
                # print(self.scrollBar.maximum())

        except Exception as e:
            print(f"Error in update_plot: {e}")

    def update_text(self, text):
        # 滚动显示最新40行文本数据
        current_text = self.text_edit.toPlainText()
        new_text = '\n'.join([current_text, text])
        self.text_edit.setPlainText('\n'.join(new_text.splitlines()[-40:]))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
