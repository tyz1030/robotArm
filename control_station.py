#!/usr/bin/env python
import sys
import cv2
import csv
import numpy as np
import time
from functools import partial

from PyQt4.QtCore import (QThread, Qt, pyqtSignal, pyqtSlot, QTimer)
from PyQt4.QtGui import (QPixmap, QImage, QApplication, QWidget, QLabel, QMainWindow, QCursor)

import os
os.sys.path.append('dynamixel/') # Path setting
from dynamixel_XL import *
from dynamixel_AX import *
from dynamixel_MX import *
from dynamixel_bus import *

from ui import Ui_MainWindow
from rexarm import Rexarm
from kinect import Kinect
from trajectory_planner import TrajectoryPlanner
from state_machine import StateMachine


""" Radians to/from  Degrees conversions """
D2R = 3.141592/180.0
R2D = 180.0/3.141592
#pixel Positions of image in GUI
MIN_X = 240
MAX_X = 880
MIN_Y = 40
MAX_Y = 520

""" Serial Port Parameters"""
BAUDRATE   = 1000000
DEVICENAME = "/dev/ttyACM0".encode('utf-8')

"""Threads"""
class VideoThread(QThread):
    updateFrame = pyqtSignal(QImage, QImage, QImage)

    def __init__(self, kinect, parent=None):
        QThread.__init__(self, parent=parent) 
        self.kinect = kinect

    def run(self):
        while True:
            self.kinect.captureVideoFrame()
            self.kinect.captureDepthFrame()
            rgb_frame = self.kinect.convertFrame()
            depth_frame = self.kinect.convertDepthFrame()
            detect_frame = self.kinect.convertDetectFrame()
            self.updateFrame.emit(rgb_frame, depth_frame, detect_frame)
            time.sleep(.03)

class LogicThread(QThread):   
    def __init__(self, state_machine, parent=None):
        QThread.__init__(self, parent=parent) 
        self.sm=state_machine

    def run(self):
        while True:    
            self.sm.run()
            time.sleep(0.05)

class DisplayThread(QThread):
    updateStatusMessage = pyqtSignal(str)
    updateJointReadout = pyqtSignal(list)
    updateEndEffectorReadout = pyqtSignal(list)

    def __init__(self, rexarm, state_machine, parent=None):
        QThread.__init__(self, parent=parent) 
        self.rexarm = rexarm
        self.sm=state_machine

    def run(self):
        while True:
            self.updateStatusMessage.emit(self.sm.status_message)
            self.updateJointReadout.emit(self.rexarm.joint_angles_fb)
            self.updateEndEffectorReadout.emit(self.rexarm.get_wrist_pose())   
            time.sleep(0.1)
    
"""GUI Class"""
class Gui(QMainWindow):
    """ 
    Main GUI Class
    contains the main function and interfaces between 
    the GUI and functions
    """
    def __init__(self,parent=None):
        QWidget.__init__(self,parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        """ Set GUI to track mouse """
        QWidget.setMouseTracking(self,True)

        """dynamixel bus -- add other motors here"""
        self.dxlbus = DXL_BUS(DEVICENAME, BAUDRATE)
        port_num = self.dxlbus.port()
        base = DXL_MX(port_num, 0)
        shld = DXL_MX(port_num, 1)
        elbw = DXL_MX(port_num, 2)
        wrst = DXL_AX(port_num, 3)
        wrst2 = DXL_XL(port_num, 4)
        grip = DXL_XL(port_num, 5)

        """Objects Using Other Classes"""
        self.rexarm = Rexarm((base,shld,elbw,wrst,wrst2),grip)
        self.kinect = Kinect(self.rexarm)
        self.tp = TrajectoryPlanner(self.rexarm)
        self.sm = StateMachine(self.rexarm, self.tp, self.kinect)
    
        """ 
        Attach Functions to Buttons & Sliders
        TODO: NAME AND CONNECT BUTTONS AS NEEDED
        """
        self.ui.btn_estop.clicked.connect(self.estop)
        self.ui.btnUser1.setText("Calibrate")
        self.ui.btnUser1.clicked.connect(partial(self.sm.set_next_state, "calibrate"))
        self.ui.sldrBase.valueChanged.connect(self.sliderChange)
        self.ui.sldrShoulder.valueChanged.connect(self.sliderChange)
        self.ui.sldrElbow.valueChanged.connect(self.sliderChange)
        self.ui.sldrWrist.valueChanged.connect(self.sliderChange)

### sliders gripper
        self.ui.sldrGrip1.valueChanged.connect(self.sliderChange)
        self.ui.sldrGrip2.valueChanged.connect(self.sliderChange)

### button gripper open & close
        self.ui.btnUser5.clicked.connect(self.btn2clicked)
        self.ui.btnUser6.clicked.connect(self.btn1clicked)



        self.ui.sldrMaxTorque.valueChanged.connect(self.sliderChange)
        self.ui.sldrSpeed.valueChanged.connect(self.sliderChange)
        self.ui.chk_directcontrol.stateChanged.connect(self.directControlChk)
        self.ui.rdoutStatus.setText("Waiting for input")
        self.ui.btn_exec.clicked.connect(partial(self.sm.set_next_state, "execute"))

        self.ui.btnUser2.setText("Record wp")
        self.ui.btnUser3.setText("Clear wp")
        self.ui.btnUser4.setText("Click and pick")
        self.ui.btnUser2.clicked.connect(partial(self.sm.set_next_state, "add_wp"))
        self.ui.btnUser3.clicked.connect(partial(self.sm.set_next_state, "clear_wp"))
        self.ui.btnUser4.clicked.connect(partial(self.sm.set_next_state, "click_and_pick"))
        self.ui.btnUser7.setText("Save Calibration Points")
        self.ui.btnUser8.setText("Load Previous Calibration")
        self.ui.btnUser7.clicked.connect(partial(self.sm.set_next_state, "save_calibration_points"))
        self.ui.btnUser8.clicked.connect(partial(self.sm.set_next_state, "load_previous_calibration"))
        self.ui.btnUser9.setText("Record Block Position")
        self.ui.btnUser9.clicked.connect(partial(self.sm.set_next_state, "record_block_position"))
        self.ui.btnUser5.setText("Open Gripper")
        self.ui.btnUser6.setText("Close Gripper")

        self.ui.btn_task1.clicked.connect(partial(self.sm.set_next_state, "mirror"))

        self.ui.btn_task2.clicked.connect(partial(self.sm.set_next_state, "stack_3"))
        self.ui.btn_task3.clicked.connect(partial(self.sm.set_next_state, "line_em_up"))
        self.ui.btn_task4.clicked.connect(partial(self.sm.set_next_state, "stack_em_high"))

        self.ui.btn_exec_6.clicked.connect(partial(self.sm.set_next_state, "pyramid5"))


        """initalize manual control off"""
        self.ui.SliderFrame.setEnabled(False)

        """initalize rexarm"""
        self.rexarm.initialize()

        """Setup Threads"""
        self.videoThread = VideoThread(self.kinect)
        self.videoThread.updateFrame.connect(self.setImage)        
        self.videoThread.start()

        
        self.logicThread = LogicThread(self.sm)
        self.logicThread.start()
        

        self.displayThread = DisplayThread(self.rexarm, self.sm)
        self.displayThread.updateJointReadout.connect(self.updateJointReadout)
        self.displayThread.updateEndEffectorReadout.connect(self.updateEndEffectorReadout)
        self.displayThread.updateStatusMessage.connect(self.updateStatusMessage)
        self.displayThread.start()

        """ 
        Setup Timer 
        this runs the trackMouse function every 50ms
        """
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.trackMouse)
        self._timer.start(50)

    """ Slots attach callback functions to signals emitted from threads"""

    @pyqtSlot(QImage, QImage, QImage)
    def setImage(self, rgb_image, depth_image, detect_image):
        if(self.ui.radioVideo.isChecked()):
            self.ui.videoDisplay.setPixmap(QPixmap.fromImage(rgb_image))
        if(self.ui.radioDepth.isChecked()):
            self.ui.videoDisplay.setPixmap(QPixmap.fromImage(depth_image))
        if(self.ui.radioDetect.isChecked()):
            self.ui.videoDisplay.setPixmap(QPixmap.fromImage(detect_image))

    @pyqtSlot(list)
    def updateJointReadout(self, joints):
        self.ui.rdoutBaseJC.setText(str("%+.2f" % (joints[0]*R2D)))
        self.ui.rdoutShoulderJC.setText(str("%+.2f" % ((joints[1]*R2D)+90.0)))
        self.ui.rdoutElbowJC.setText(str("%+.2f" % (joints[2]*R2D)))
        self.ui.rdoutWristJC.setText(str("%+.2f" % (joints[3]*R2D)))
###
        #self.ui.rdoutGrip1.setText(str("%+.2f" % (joints[4]*R2D)))
        #self.ui.rdoutGrip2.setText(str("%+.2f" % (joints[5]*R2D)))
###

    @pyqtSlot(list)
    def updateEndEffectorReadout(self, pos):
        self.ui.rdoutX.setText(str("%+.2f" % (pos[0])))
        self.ui.rdoutY.setText(str("%+.2f" % (pos[1])))
        self.ui.rdoutZ.setText(str("%+.2f" % (pos[2])))
        self.ui.rdoutT.setText(str("%+.2f" % (pos[3])))

    @pyqtSlot(str)
    def updateStatusMessage(self, msg):
        self.ui.rdoutStatus.setText(msg)


    """ Other callback functions attached to GUI elements"""

    def estop(self):
        self.rexarm.estop = True
        self.sm.set_next_state("estop")

    def sliderChange(self):
        """ 
        Function to change the slider labels when sliders are moved
        and to command the arm to the given position
        """
        self.ui.rdoutBase.setText(str(self.ui.sldrBase.value()))
        self.ui.rdoutShoulder.setText(str(self.ui.sldrShoulder.value()))
        self.ui.rdoutElbow.setText(str(self.ui.sldrElbow.value()))
        self.ui.rdoutWrist.setText(str(self.ui.sldrWrist.value()))
###
        self.ui.rdoutGrip1.setText(str(self.ui.sldrGrip1.value()))
        self.ui.rdoutGrip2.setText(str(self.ui.sldrGrip2.value()))
###
        self.ui.rdoutTorq.setText(str(self.ui.sldrMaxTorque.value()) + "%")
        self.ui.rdoutSpeed.setText(str(self.ui.sldrSpeed.value()) + "%")
        self.rexarm.set_torque_limits([self.ui.sldrMaxTorque.value()/100.0]*self.rexarm.num_joints, update_now = False)
        self.rexarm.set_speeds_normalized_global(self.ui.sldrSpeed.value()/100.0, update_now = False)     
###
        joint_positions = np.array([self.ui.sldrBase.value()*D2R, 
                           self.ui.sldrShoulder.value()*D2R,
                           self.ui.sldrElbow.value()*D2R,
                           self.ui.sldrWrist.value()*D2R,
                            (self.ui.sldrGrip1.value())*D2R])

        
        self.rexarm.set_positions(joint_positions, update_now = False)

### 
    def btn1clicked(self):
        self.rexarm.close_gripper()

    def btn2clicked(self):
        self.rexarm.open_gripper()

    def btn3clicked(self):
        initdeg = -39.5
        self.rexarm.set_gripper_rotate(initdeg)

    def directControlChk(self, state):
        if state == Qt.Checked:
            self.sm.set_next_state("manual")
            self.ui.SliderFrame.setEnabled(True)
        else:
            self.sm.set_next_state("idle")
            self.ui.SliderFrame.setEnabled(False)

    def trackMouse(self):
        """ 
        Mouse position presentation in GUI
        TODO: after implementing workspace calibration 
        display the world coordinates the mouse points to 
        in the RGB video image.
        """

        x = QWidget.mapFromGlobal(self,QCursor.pos()).x()
        y = QWidget.mapFromGlobal(self,QCursor.pos()).y()
        if ((x < MIN_X) or (x >= MAX_X) or (y < MIN_Y) or (y >= MAX_Y)):
            self.ui.rdoutMousePixels.setText("(-,-,-)")
            self.ui.rdoutMouseWorld.setText("(-,-,-)")
        else:
            x = x - MIN_X
            y = y - MIN_Y
            
            """color calibration"""
            #color = self.kinect.colorDetector(x,y)
            #self.kinect.colorCalibration(x,y)
            #self.kinect.block_detection_verification(x,y)
            # map real world
            real_x = self.kinect.real_coord[x][y][0]
            real_y = self.kinect.real_coord[x][y][1]

            if(self.kinect.currentDepthFrame.any() != 0):
                z = self.kinect.currentDepthFrame[y][x]
                real_z = self.kinect.convertDepthtomm(z)
                self.ui.rdoutMousePixels.setText("(%.0f,%.0f,%.0f)" % (x,y,z))
                if self.kinect.kinectCalibrated == True:
                    self.ui.rdoutMouseWorld.setText("(%.0f,%.0f,%.0f)" % (real_x,real_y,real_z))
                else:
                    self.ui.rdoutMouseWorld.setText("(-,-,-)")

    def mousePressEvent(self, QMouseEvent):
        """ 
        Function used to record mouse click positions for calibration 
        """
 
        """ Get mouse posiiton """
        x = QMouseEvent.x()
        y = QMouseEvent.y()

        """ If mouse position is not over the camera image ignore """
        if ((x < MIN_X) or (x > MAX_X) or (y < MIN_Y) or (y > MAX_Y)): return

        """ Change coordinates to image axis """
        self.kinect.last_click[0] = x - MIN_X 
        self.kinect.last_click[1] = y - MIN_Y
        self.kinect.new_click = True
        #print(self.kinect.last_click)
    
    def shutdown(self):
        self.rexarm.shutdown()

    def closeEvent(self, *args, **kwargs):
        super(QMainWindow, self).closeEvent(*args, **kwargs)
        print("EXITING...")
        self.shutdown()

"""main function"""
def main():
    app = QApplication(sys.argv)
    app_window = Gui()
    app_window.show()
    sys.exit(app.exec_())
 
if __name__ == '__main__':
    main()
