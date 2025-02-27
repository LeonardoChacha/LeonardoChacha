#!/usr/bin/python3
# coding=utf8
import sys
import cv2
import import_path
import math
import time
import Camera
import numpy as np
import yaml_handle
import kinematics as kinematics
from HiwonderSDK.PID import PID
import HiwonderSDK.Misc as Misc
import HiwonderSDK.Board as Board

ik = kinematics.IK()

debug = False
HWSONAR = None

if sys.version_info.major == 2:
    print('Please run this program with python3!')
    sys.exit(0)

range_rgb = {
    'red': (0, 0, 255),
    'blue': (255, 0, 0),
    'green': (0, 255, 0),
    'black': (0, 0, 0),
    'white': (255, 255, 255),
}

lab_data = None
servo_data = None
def load_config():
    global lab_data, servo_data
    
    lab_data = yaml_handle.get_yaml_data(yaml_handle.lab_file_path)
    servo_data = yaml_handle.get_yaml_data(yaml_handle.servo_file_path)

load_config()

__target_color = ('green',)
# 设置检测颜色
def setTargetColor(target_color):
    global __target_color

    __target_color = target_color
    return (True, ())

# 找出面积最大的轮廓
# 参数为要比较的轮廓的列表
def getAreaMaxContour(contours):
    contour_area_temp = 0
    contour_area_max = 0

    area_max_contour = None
    max_area = 0

    for c in contours:  # 历遍所有轮廓
        contour_area_temp = math.fabs(cv2.contourArea(c))  # 计算轮廓面积
        if contour_area_temp > contour_area_max:
            contour_area_max = contour_area_temp
            if contour_area_temp > 50:  # 只有在面积大于设定时，最大面积的轮廓才是有效的，以过滤干扰
                area_max_contour = c
                max_area = contour_area_temp

    return area_max_contour, max_area  # 返回最大的轮廓

x_dis = servo_data['servo2']
y_dis = 1500
# 初始位置
def initMove():
    HWSONAR.setRGBMode(0)
    HWSONAR.setRGB(1, (0, 0, 0))
    HWSONAR.setRGB(2, (0, 0, 0))     
    Board.setPWMServoPulse(1, y_dis, 500)
    Board.setPWMServoPulse(2, x_dis, 500)   

x_pid = PID(P=0.4, I=0.02, D=0.02)#pid初始化
y_pid = PID(P=0.4, I=0.02, D=0.02)
# 变量重置
def reset():
    global x_dis, y_dis
    global __target_color
       
    x_dis = servo_data['servo2']
    y_dis = 1500
    x_pid.clear()
    y_pid.clear()
    __target_color = ()
    HWSONAR.setRGBMode(0)
    HWSONAR.setRGB(1, (0, 0, 0))
    HWSONAR.setRGB(2, (0, 0, 0))
    initMove()

# app初始化调用
def init():
    print("ColorTrack Init")
    load_config()
    reset()

__isRunning = False
# app开始玩法调用
def start():
    global __isRunning
    __isRunning = True
    print("ColorTrack Start")

# app停止玩法调用
def stop():
    global __isRunning
    __isRunning = False
    reset()
    print("ColorTrack Stop")

# app退出玩法调用
def exit():
    global __isRunning
    __isRunning = False
    ik.stand(ik.initial_pos)
    print("ColorTrack Exit")

def hisEqulColor(img):
    ycrcb = cv2.cvtColor(img, cv2.COLOR_BGR2YCR_CB)
    channels = cv2.split(ycrcb)
    cv2.equalizeHist(channels[0], channels[0])
    cv2.merge(channels, ycrcb)
    img_eq = cv2.cvtColor(ycrcb, cv2.COLOR_YCR_CB2BGR)
    return img_eq

size = (320, 240)
def run(img):
    global x_dis, y_dis
    
    img_copy = img.copy()
    img_h, img_w = img.shape[:2]
    
    if not __isRunning or __target_color == ():
        return img

    cv2.line(img, (int(img_w/2 - 10), int(img_h/2)), (int(img_w/2 + 10), int(img_h/2)), (0, 255, 255), 2)
    cv2.line(img, (int(img_w/2), int(img_h/2 - 10)), (int(img_w/2), int(img_h/2 + 10)), (0, 255, 255), 2)

    img_hisEqul = hisEqulColor(img_copy)
   
    frame_resize = cv2.resize(img_hisEqul, size, interpolation=cv2.INTER_NEAREST)
    frame_gb = cv2.GaussianBlur(frame_resize, (5, 5), 5)   
    frame_lab = cv2.cvtColor(frame_gb, cv2.COLOR_BGR2LAB)  # 将图像转换到LAB空间
    
    area_max = 0
    areaMaxContour = 0
    for i in lab_data:
        if i in __target_color:
            detect_color = i
            frame_mask = cv2.inRange(frame_lab,
                                         (lab_data[i]['min'][0],
                                          lab_data[i]['min'][1],
                                          lab_data[i]['min'][2]),
                                         (lab_data[i]['max'][0],
                                          lab_data[i]['max'][1],
                                          lab_data[i]['max'][2]))  #对原图像和掩模进行位运算
            eroded = cv2.erode(frame_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))  #腐蚀
            dilated = cv2.dilate(eroded, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))) #膨胀
            if debug:
                cv2.imshow(i, dilated)
            contours = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[-2]  # 找出轮廓
            areaMaxContour, area_max = getAreaMaxContour(contours)  # 找出最大轮廓

# Dentro de la función run:
    if area_max > 50:  # Si hay una pelota detectada
        (_, centerY), _ = cv2.minEnclosingCircle(areaMaxContour)  # Obtener el centro vertical de la pelota
        centerY = int(Misc.map(centerY, 0, size[1], 0, img_h))  # Mapear al tamaño de la imagen original

        # Actualizar el servo vertical basado en la posición vertical de la pelota
        y_pid.SetPoint = img_h / 2
        y_pid.update(centerY)
        dy = int(y_pid.output)
        y_dis += dy

        # Limitar los valores de y_dis para evitar moverse fuera de los límites
        y_dis = 1000 if y_dis < 1000 else y_dis
        y_dis = 2000 if y_dis > 2000 else y_dis

        # Actualizar la posición del servo vertical
        if not debug:
            Board.setPWMServoPulse(1, y_dis, 20)
            time.sleep(0.02)

    # Establecer una posición fija para el eje horizontal (por ejemplo, en el centro)
    x_dis = 1500  # Esta es una posición de ejemplo, puedes ajustarla según sea necesario

            
    return img

if __name__ == '__main__':
    import HiwonderSDK.Sonar as Sonar
    from CameraCalibration.CalibrationConfig import *
    
    #加载参数
    param_data = np.load(calibration_param_path + '.npz')

    #获取参数
    mtx = param_data['mtx_array']
    dist = param_data['dist_array']
    newcameramtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (640, 480), 0, (640, 480))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, newcameramtx, (640, 480), 5)
    
    debug = False
    if debug:
        print('Debug Mode')
    
    HWSONAR = Sonar.Sonar()
    init()
    start()
    __target_color = ('green',)
    my_camera = Camera.Camera()
    my_camera.camera_open()
    while True:
        img = my_camera.frame
        if img is not None:
            frame = img.copy()
            frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)  # 畸变矫正
            Frame = run(frame)           
            cv2.imshow('Frame', Frame)
            key = cv2.waitKey(1)
            if key == 27:
                break
        else:
            time.sleep(0.01)
    my_camera.camera_close()
    cv2.destroyAllWindows()