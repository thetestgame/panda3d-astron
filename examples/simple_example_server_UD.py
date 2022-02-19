#!/usr/bin/env python

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d_astron.repository import AstronInternalRepository
from direct.directnotify.DirectNotifyGlobal import directNotify
from panda3d.core import loadPrcFileData
from time import sleep

# Globally known object and channel IDs
from simple_example_globals_server import LoginManagerId, UDChannel, SSChannel

# No camera or window is needed, but notifications are.
loadPrcFileData("", "\n".join(["window-type none",
                               "notify-level-udserver debug"]))
notify = directNotify.newCategory("udserver")

# This class manages the UberDOGs, which in this case is just one, the login
# manager.
class SimpleServer(ShowBase):

    def __init__(self, server_framerate = 60):
        ShowBase.__init__(self)
        self.startUberDOG()

    def startUberDOG(self):
        notify.info("Starting UberDOG")
        # UberDOG repository
        air = AstronInternalRepository(UDChannel,                           # Repository channel
                                       serverId = SSChannel,                # Stateserver channel
                                       dcFileNames = ["simple_example.dc"],
                                       dcSuffix = "UD",
                                       connectMethod = AstronInternalRepository.CM_NET)
        air.connect("127.0.0.1", 7199)
        air.districtId = air.GameGlobalsId = UDChannel
        
        # Create the LoginManager
        self.login_manager = air.generateGlobalObject(LoginManagerId, 'LoginManager')

simple_server = SimpleServer()
simple_server.run()
