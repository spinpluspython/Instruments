from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel, QPushButton, QDoubleSpinBox, QRadioButton, QLineEdit, QVBoxLayout, QStackedWidget, QHBoxLayout, QApplication, QComboBox, QFrame
from PyQt5 import QtCore
from  PyQt5.QtGui import QColor
from functools import partial


class DelayStageWidget(QWidget):


    def __init__(self, parent=None):
        #QWidget.__init__(self, parent=parent)
        super().__init__()

        self.stepsize = 0.0
        self.currentPos = 0.0

        self.col = QColor(255, 0, 0)
        self.lay = QGridLayout(self)
        self.leftButton = QPushButton("<-")
        self.rightButton = QPushButton("->")
        self.disConnectButton = QPushButton("connect")
        self.mmRButton = QRadioButton("mm")
        self.psRButton = QRadioButton("ps")
        self.setCurPosAsZero = QPushButton("Set current position as zero")

        self.stepsizeSpinner = QDoubleSpinBox()
        self.stepsizeSpinner.setRange(0, 150)
        self.stepsizeSpinner.setValue(0.0)
        self.stepsizeSpinner.setDecimals(3)


        self.moveToSpinner = QDoubleSpinBox()
        self.moveToSpinner.setRange(-150, 150)
        self.moveToSpinner.setValue(0.0)
        self.moveToSpinner.setDecimals

        self.moveToButton = QPushButton("Move to:")


        self.posLabel = QLabel("Current position:  00.00")

        self.square = QFrame(self)
        self.square.setGeometry(150, 20, 10, 10)
        self.square.setStyleSheet("QWidget { background-color: %s }" %
                                  self.col.name())

        self.lay.addWidget(QLabel("Delay Stage"), 0, 0, 1, 1)
        self.lay.addWidget(self.square, 1,0, 1, 1)
        self.lay.addWidget(self.disConnectButton, 1 ,1, 1, 2)
        self.lay.addWidget(self.mmRButton, 1, 5, 1, 1)
        self.lay.addWidget(self.psRButton, 2, 5, 1, 1)
        self.lay.addWidget(self.leftButton, 2, 0)
        self.lay.addWidget(self.rightButton, 2, 3, 1, 2)
        self.lay.addWidget(QLabel("Stepsize"), 2, 1, 1, 1)
        self.lay.addWidget(self.stepsizeSpinner, 2, 2,1,1)
        self.lay.addWidget(self.posLabel, 3,0,1,2)
        self.lay.addWidget(self.moveToButton, 4, 0, 1, 1)
        self.lay.addWidget(self.moveToSpinner, 4, 1, 1, 1)
        self.lay.addWidget(self.setCurPosAsZero, 5, 0, 1, 3)


        self.disConnectButton.clicked.connect(self.dis_connect)
        self.stepsizeSpinner.valueChanged.connect(self.set_Stepsize)
        self.rightButton.clicked.connect(self.move_Right)
        self.leftButton.clicked.connect(self.move_Left)
        self.setCurPosAsZero.clicked.connect(self.set_Cur_Pos_As_Zero)
        self.moveToButton.clicked.connect(self.move_to)


    def dis_connect(self):
        if self.disConnectButton.text() == "connect":
            self.col.setGreen(255)
            self.col.setRed(0)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("disconnect")
        else:
            self.col.setGreen(0)
            self.col.setRed(255)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("connect")


    def set_Stepsize(self, size):
        self.stepsize = size

    def move_Right(self):
        self.currentPos += self.stepsize
        self.posLabel.setText("Current position:  " + str(self.currentPos))

    def move_Left(self):
        self.currentPos -= self.stepsize
        self.posLabel.setText("Current position:  " +str(self.currentPos))

    def set_Cur_Pos_As_Zero(self):
        self.currentPos = 0.0
        self.posLabel.setText("Current position:  " + str(self.currentPos))

    def move_to(self):
        goto = self.moveToSpinner.value()
        self.currentPos = goto
        self.posLabel.setText("Current position:  " + str(self.currentPos))

    def setValues(self):
        valueList=[self.startButton.text()]
        stepList=[]
        for i in self.buttonList:
            valueList.append(i[0].text())
            stepList.append(i[1].text())
        print(valueList)
        self.setTimeScale.emit(valueList, stepList)


class LockinWidget(QWidget):

    def __init__(self, parent=None):
        #QWidget.__init__(self, parent=parent)
        super().__init__()
        self.col = QColor(255, 0, 0)
        self.lay = QGridLayout(self)

        self.square = QFrame(self)
        self.square.setGeometry(150, 20, 10, 10)
        self.square.setStyleSheet("QWidget { background-color: %s }" %
                                  self.col.name())

        self.disConnectButton = QPushButton("connect")
        self.lay.addWidget(QLabel("Lockin"), 0,0)
        self.lay.addWidget(self.square, 1, 0)
        self.lay.addWidget(self.disConnectButton, 1, 1)
        self.disConnectButton.clicked.connect(self.dis_connect)


    def dis_connect(self):
        if self.disConnectButton.text() == "connect":
            self.col.setGreen(255)
            self.col.setRed(0)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("disconnect")
        else:
            self.col.setGreen(0)
            self.col.setRed(255)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("connect")




class CryostatWidget(QWidget):


    def __init__(self, parent=None):
        #QWidget.__init__(self, parent=parent)
        super().__init__()

        self.col = QColor(255, 0, 0)
        self.lay = QGridLayout(self)

        self.square = QFrame(self)
        self.square.setGeometry(150, 20, 10, 10)
        self.square.setStyleSheet("QWidget { background-color: %s }" %
                                  self.col.name())

        self.disConnectButton = QPushButton("connect")
        self.currentTemp = QLabel("Current Temperature:   0.00")
        self.setTempSpinner = QDoubleSpinBox()
        self.setTempSpinner.setRange(-150, 150)
        self.setTempSpinner.setValue(0.0)
        self.setTempSpinner.setDecimals(3)
        self.setTempButton = QPushButton("Set Temperature")


        self.lay.addWidget(QLabel("Cryostat"),0,0)
        self.lay.addWidget(self.square,1,0)
        self.lay.addWidget(self.disConnectButton,1,1)
        self.lay.addWidget(self.currentTemp, 2,0)
        self.lay.addWidget(QLabel("Set Temperature"),3,0)
        self.lay.addWidget(self.setTempSpinner, 3,1)
        self.lay.addWidget(self.setTempButton, 3,2)

        self.disConnectButton.clicked.connect(self.dis_connect)
        self.setTempButton.clicked.connect(self.set_Temp)

    def dis_connect(self):
        if self.disConnectButton.text() == "connect":
            self.col.setGreen(255)
            self.col.setRed(0)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("disconnect")
        else:
            self.col.setGreen(0)
            self.col.setRed(255)
            self.square.setStyleSheet("QFrame { background-color: %s }" %
                                      self.col.name())
            self.disConnectButton.setText("connect")

    def set_Temp(self):
        self.currentTemp.setText("Current Temperature:   " + str(self.setTempSpinner.value()))

class StackedExample2(QWidget):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent=parent)

        self.objectsList = ["DelayStage", "Lockin", "Cryostat"]
        self.objectDict = {"DelayStage" : DelayStageWidget, "Lockin": LockinWidget, "Cryostat" : CryostatWidget}
        btnList= []
        self.widgetList = [self.objectDict[i] for i in self.objectsList]
        print(self.widgetList)

        self.lay = QVBoxLayout(self)
        self.Stack = QStackedWidget()
        for i in self.widgetList:
            self.Stack.addWidget(i())
        #self.Stack.addWidget(DelayStageWidget())
        #self.Stack.addWidget(LockinWidget())
        #self.Stack.addWidget(CryostatWidget())

        btnLayout = QHBoxLayout()

        for i in range(0, len(self.objectsList)):
            btnList.append(QPushButton(self.objectsList[i]))
            #btnList[i].clicked.connect(lambda: self.goTo(i))
            btnList[i].clicked.connect(partial(self.goTo, i))
            btnLayout.addWidget(btnList[i])

        self.lay.addWidget(self.Stack)
        self.lay.addLayout(btnLayout)

    def goTo(self, i):
        self.Stack.setCurrentIndex(i)





if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)
    w = StackedExample2()
    w.show()
    sys.exit(app.exec_())