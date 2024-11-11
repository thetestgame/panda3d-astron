from direct.directnotify import DirectNotifyGlobal
from direct.distributed.ClientRepositoryBase import ClientRepositoryBase
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.MsgTypes import *
from direct.showbase import ShowBase # __builtin__.config
from direct.task.TaskManagerGlobal import * # taskMgr
from direct.distributed.PyDatagramIterator import PyDatagramIterator
from direct.distributed import DoInterestManager as interest_mgr

from panda3d_astron import msgtypes

# --------------------------------------------------------------------------------------------------------------------------------------------------------------------- #
# Panda3D ClientRepositoryBase implementation for implementing Astron clients

class AstronClientRepository(ClientRepositoryBase):
    """
    The Astron implementation of a clients repository for
    communication with an Astron ClientAgent.

    This repo will emit events for:
    * CLIENT_HELLO_RESP
    * CLIENT_EJECT ( error_code, reason )
    * CLIENT_OBJECT_LEAVING ( do_id )
    * CLIENT_ADD_INTEREST ( context, interest_id, parent_id, zone_id )
    * CLIENT_ADD_INTEREST_MULTIPLE ( icontext, interest_id, parent_id, [zone_ids] )
    * CLIENT_REMOVE_INTEREST ( context, interest_id )
    * CLIENT_DONE_INTEREST_RESP ( context, interest_id )
    * LOST_CONNECTION ()
    """

    notify = DirectNotifyGlobal.directNotify.newCategory("repository")

    # This is required by DoCollectionManager, even though it's not
    # used by this implementation.
    GameGlobalsId = 0

    def __init__(self, *args, **kwargs):
        ClientRepositoryBase.__init__(self, *args, **kwargs)
        base.finalExitCallbacks.append(self.shutdown)
        self.message_handlers = {
            msgtypes.CLIENT_HELLO_RESP: self.handleHelloResp,
            msgtypes.CLIENT_EJECT: self.,
            msgtypes.CLIENT_ENTER_OBJECT_REQUIRED: self.handleEnterObjectRequired,
            msgtypes.CLIENT_ENTER_OBJECT_REQUIRED_OTHER: self.handleEnterObjectRequiredOther,
            msgtypes.CLIENT_ENTER_OBJECT_REQUIRED_OWNER: self.handleEnterObjectRequiredOwner,
            msgtypes.CLIENT_ENTER_OBJECT_REQUIRED_OTHER_OWNER: self.handleEnterObjectRequiredOtherOwner,
            msgtypes.CLIENT_OBJECT_SET_FIELD: self.handleUpdateField,
            msgtypes.CLIENT_OBJECT_SET_FIELDS: self.handleUpdateFields,
            msgtypes.CLIENT_OBJECT_LEAVING: self.handleObjectLeaving,
            msgtypes.CLIENT_OBJECT_LOCATION: self.handleObjectLocation,
            msgtypes.CLIENT_ADD_INTEREST: self.handleAddInterest,
            msgtypes.CLIENT_ADD_INTEREST_MULTIPLE: self.handleAddInterestMultiple,
            msgtypes.CLIENT_REMOVE_INTEREST: self.handleRemoveInterest,
            msgtypes.CLIENT_DONE_INTEREST_RESP: self.handleInterestDoneMessage,
        }

    def handleDatagram(self, di: PyDatagramIterator) -> None:
        """
        Handles incoming datagrams from an Astron ClientAgent instance.
        """

        msg_type = self.getMsgType()
        message_handler = self.message_handlers.get(msg_type, None)
        if message_handler is None:
            self.notify.error('Received unknown message type: %d!' % msg_type)
            return

        message_handler(di)
        self.consider_heartbeat()

    handle_datagram = handleDatagram

    def consider_heartbeat(self) -> None:
        """
        Sends a heartbeat message to the Astron client agent if one has not been sent recently.
        """

        super().considerHeartbeat()

    def handleHelloResp(self, di: PyDatagramIterator) -> None:
        """
        Handles the CLIENT_HELLO_RESP packet sent by the Client Agent to the client when the client's CLIENT_HELLO is accepted.
        """

        messenger.send("CLIENT_HELLO_RESP", [])

    def handleEject(self, di: PyDatagramIterator) -> None:
        """
        Handles the CLIENT_DISCONNECT sent by the client to the Client Agent to notify that it is going to close the connection.
        """

        error_code = di.get_uint16()
        reason = di.get_string()
        messenger.send("CLIENT_EJECT", [error_code, reason])

    def handleEnterObjectRequired(self, di: PyDatagramIterator) -> None:
        """
        """

        do_id = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        dclass = self.dclassesByNumber[dclass_id]
        self.generateWithRequiredFields(dclass, do_id, di, parent_id, zone_id)

    def handleEnterObjectRequiredOther(self, di: PyDatagramIterator) -> None:
        """
        """

        do_id = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        dclass = self.dclassesByNumber[dclass_id]
        self.generateWithRequiredOtherFields(dclass, do_id, di, parent_id, zone_id)

    def handleEnterObjectRequiredOwner(self, di: PyDatagramIterator) -> None:
        """
        """

        avatar_doId = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        dclass = self.dclassesByNumber[dclass_id]
        self.generateWithRequiredFieldsOwner(dclass, avatar_doId, di)

    def handleEnterObjectRequiredOtherOwner(self, di: PyDatagramIterator) -> None:
        """
        """

        avatar_doId = di.get_uint32()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()
        dclass_id = di.get_uint16()
        dclass = self.dclassesByNumber[dclass_id]
        self.generateWithRequiredOtherFieldsOwner(dclass, avatar_doId, di)

    def generateWithRequiredFieldsOwner(self, dclass: object, doId: int, di: PyDatagramIterator) -> None:
        """
        """

        if doId in self.doId2ownerView:
            # ...it is in our dictionary.
            # Just update it.
            self.notify.error('duplicate owner generate for %s (%s)' % (
                doId, dclass.getName()))
            distObj = self.doId2ownerView[doId]
            assert distObj.dclass == dclass
            distObj.generate()
            distObj.updateRequiredFields(dclass, di)
            # updateRequiredFields calls announceGenerate
        elif self.cacheOwner.contains(doId):
            # ...it is in the cache.
            # Pull it out of the cache:
            distObj = self.cacheOwner.retrieve(doId)
            assert distObj.dclass == dclass
            # put it in the dictionary:
            self.doId2ownerView[doId] = distObj
            # and update it.
            distObj.generate()
            distObj.updateRequiredFields(dclass, di)
            # updateRequiredFields calls announceGenerate
        else:
            # ...it is not in the dictionary or the cache.
            # Construct a new one
            classDef = dclass.getOwnerClassDef()
            if classDef == None:
                self.notify.error("Could not create an undefined %s object. Have you created an owner view?" % (dclass.getName()))
            distObj = classDef(self)
            distObj.dclass = dclass
            # Assign it an Id
            distObj.doId = doId
            # Put the new do in the dictionary
            self.doId2ownerView[doId] = distObj
            # Update the required fields
            distObj.generateInit()  # Only called when constructed
            distObj.generate()
            distObj.updateRequiredFields(dclass, di)
            # updateRequiredFields calls announceGenerate
        return distObj

    generate_with_required_Fields_owner = generateWithRequiredFieldsOwner

    def handleUpdateFields(self, di):
        """
        """

        # Can't test this without the server actually sending it.
        self.notify.error("CLIENT_OBJECT_SET_FIELDS not implemented!")
        # # Here's some tentative code and notes:
        # do_id = di.getUint32()
        # field_count = di.getUint16()
        # for i in range(0, field_count):
        #     field_id = di.getUint16()
        #     field = self.get_dc_file().get_field_by_index(field_id)
        #     # print(type(field))
        #     # print(field)
        #     # FIXME: Get field type, unpack value, create and send message.
        #     # value = di.get?()
        #     # Assemble new message

    def handleObjectLeaving(self, di):
        """
        """

        do_id = di.get_uint32()
        dist_obj = self.doId2do.get(do_id)
        dist_obj.delete()
        self.deleteObject(do_id)
        messenger.send("CLIENT_OBJECT_LEAVING", [do_id])

    def handleAddInterest(self, di):
        """
        """

        context = di.get_uint32()
        interest_id = di.get_uint16()
        parent_id = di.get_uint32()
        zone_id = di.get_uint32()

        messenger.send("CLIENT_ADD_INTEREST", [context, interest_id, parent_id, zone_id])
        self.addInternalInterestHandle(context, interest_id, parent_id, [zone_id])

    def handleAddInterestMultiple(self, di):
        """
        """

        context = di.get_uint32()
        interest_id = di.get_uint16()
        parent_id = di.get_uint32()
        zone_ids = [di.get_uint32() for i in range(0, di.get_uint16())]

        messenger.send("CLIENT_ADD_INTEREST_MULTIPLE", [context, interest_id, parent_id, zone_ids])
        self.addInternalInterestHandle(context, interest_id, parent_id, zone_ids)

    def addInternalInterestHandle(self, context, interest_id, parent_id, zone_ids) -> None:
        """
        """

        # make sure we've got parenting rules set in the DC
        if parent_id not in (self.getGameDoId(),):
            parent = self.getDo(parent_id)
            if not parent:
                self.notify.error('Attempting to add interest under unknown object %s' % parent_id)
            else:
                if not parent.hasParentingRules():
                    self.notify.error('No setParentingRules defined in the DC for object %s (%s)' % (parent_id, parent.__class__.__name__))

        interest_mgr.DoInterestManager._interests[interest_id] = interest_mgr.InterestState(
            None, interest_mgr.InterestState.StateActive, context, None, parent_id, zone_ids, self._completeEventCount, True)

    def handleRemoveInterest(self, di):
        """
        """

        context = di.get_uint32()
        interest_id = di.get_uint16()
        messenger.send("CLIENT_REMOVE_INTEREST", [context, interest_id])

    def deleteObject(self, doId):
        """
        implementation copied from ClientRepository.py
        Removes the object from the client's view of the world.  This
        should normally not be called directly except in the case of
        error recovery, since the server will normally be responsible
        for deleting and disabling objects as they go out of scope.
        After this is called, future updates by server on this object
        will be ignored (with a warning message).  The object will
        become valid again the next time the server sends a generate
        message for this doId.
        This is not a distributed message and does not delete the
        object on the server or on any other client.
        """

        if doId in self.doId2do:
            # If it is in the dictionary, remove it.
            obj = self.doId2do[doId]
            # Remove it from the dictionary
            del self.doId2do[doId]
            # Disable, announce, and delete the object itself...
            # unless delayDelete is on...
            obj.deleteOrDelay()
            if self.isLocalId(doId):
                self.freeDoId(doId)
        elif self.cache.contains(doId):
            # If it is in the cache, remove it.
            self.cache.delete(doId)
            if self.isLocalId(doId):
                self.freeDoId(doId)
        else:
            # Otherwise, ignore it
            self.notify.warning(
                "Asked to delete non-existent DistObj " + str(doId))

    delete_object = deleteObject

    def sendUpdate(self, distObj, fieldName, args):
        """ 
        Sends a normal update for a single field. 
        """

        dg = distObj.dclass.clientFormatUpdate(
            fieldName, distObj.doId, args)
        self.send(dg)

    send_update = sendUpdate

    def sendHello(self, version_string: str = None):
        """
        Sends our CLIENT_HELLO protocol handshake packet to the game server. Uses the supplied argument version if present
        otherwise default to the server-version PRC variable
        """

        if version_string == None:
            version_string = ConfigVariableString('server-version', '')

        if version_string == None or version_string == '':
            self.notify.error('No server version defined at the time of hello. Please set a "server-version" string in your panda runtime conrfiguration file')
            return

        dg = PyDatagram()
        dg.add_uint16(msgtypes.CLIENT_HELLO)
        dg.add_uint32(self.get_dc_file().get_hash())
        dg.add_string(version_string)
        self.send(dg)

    send_hello = sendHello

    def sendHeartbeat(self):
        """
        """

        datagram = PyDatagram()
        datagram.addUint16(msgtypes.CLIENT_HEARTBEAT)
        self.send(datagram)

    send_heartbeat = sendHeartbeat

    def sendAddInterest(self, context, interest_id, parent_id, zone_id):
        """
        """

        dg = PyDatagram()
        dg.add_uint16(msgtypes.CLIENT_ADD_INTEREST)
        dg.add_uint32(context)
        dg.add_uint16(interest_id)
        dg.add_uint32(parent_id)
        dg.add_uint32(zone_id)
        self.send(dg)

    send_add_interest = sendAddInterest

    def sendAddInterestMultiple(self, context, interest_id, parent_id, zone_ids):
        """
        """

        dg = PyDatagram()
        dg.add_uint16(msgtypes.CLIENT_ADD_INTEREST_MULTIPLE)
        dg.add_uint32(context)
        dg.add_uint16(interest_id)
        dg.add_uint32(parent_id)
        dg.add_uint16(len(zone_ids))
        for zone_id in zone_ids:
            dg.add_uint32(zone_id)
        self.send(dg)

    send_add_interest_multiple = sendAddInterestMultiple

    def sendRemoveInterest(self, context, interest_id):
        """
        """

        dg = PyDatagram()
        dg.add_uint16(msgtypes.CLIENT_REMOVE_INTEREST)
        dg.add_uint32(context)
        dg.add_uint16(interest_id)
        self.send(dg)

    send_remove_interest = sendRemoveInterest

    def lostConnection(self):
        """
        """

        messenger.send("LOST_CONNECTION")

    def disconnect(self):
        """
        This implicitly deletes all objects from the repository.
        """

        for do_id in self.doId2do.keys():
            self.deleteObject(do_id)
        ClientRepositoryBase.disconnect(self)