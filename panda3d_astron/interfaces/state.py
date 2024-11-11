"""
State Server Interface for Astron
"""

from direct.directnotify import DirectNotifyGlobal
from direct.distributed.PyDatagram import PyDatagram

from panda3d import direct
from panda3d import core as p3d
from panda3d_astron import msgtypes

class StateServerInterface(object):
    """
    Network interface for working with the state server
    """

    notify = DirectNotifyGlobal.directNotify.newCategory("state-server")

    def __init__(self, air: object):
        """
        Initializes the state server interface
        """

        self.air = air
        self.__callbacks = {}

    def handle_datagram(self, msg_type: int, di: object) -> None:
        """
        Handles state server datagrams
        """

        if msg_type in (msgtypes.STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED,
                       msgtypes.STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER,
                       msgtypes.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED,
                       msgtypes.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED_OTHER):
            other = msg_type == msgtypes.STATESERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER or \
                    msg_type == msgtypes.STATESERVER_OBJECT_ENTER_LOCATION_WITH_REQUIRED_OTHER
            self.handle_object_entry(di, other)
        elif msg_type in (msgtypes.STATESERVER_OBJECT_CHANGING_AI,
                         msgtypes.STATESERVER_OBJECT_DELETE_RAM):
            self.handle_object_exit(di)
        elif msg_type == msgtypes.STATESERVER_OBJECT_GET_FIELD_RESP:
            self.handle_get_field_resp(di)
        elif msg_type == msgtypes.STATESERVER_OBJECT_GET_FIELDS_RESP:
            self.handle_get_fields_resp(di)
        elif msg_type == msgtypes.STATESERVER_OBJECT_CHANGING_LOCATION:
            self.handle_obj_location(di)
        elif msg_type == msgtypes.STATESERVER_OBJECT_GET_LOCATION_RESP:
            self.handle_get_location_resp(di)
        elif msg_type == msgtypes.STATESERVER_OBJECT_GET_ALL_RESP:
            self.handle_get_object_resp(di)
        elif msg_type == msgtypes.DBSS_OBJECT_GET_ACTIVATED_RESP:
            self.handle_get_activated_resp(di)
        else:
            self.notify.warning('Received unknown state server message: %d' % msg_type)

    def create_object_with_required(self, doId: int, parentId: int, zoneId: int, dclass: direct.DClass, fields: dict) -> None:
        """
        Create an object on the State Server, specifying its initial location as (parent_id, zone_id), its class, 
        and initial field data. The object then broadcasts an ENTER_LOCATION message to its location channel, 
        and sends a CHANGING_ZONE with old location (0,0) to its parent (if it has one).

        Additionally, the object sends a GET_LOCATION to its children over the parent messages channel (1 << 32|parent_id) with context 1001 (STATESERVER_CONTEXT_WAKE_CHILDREN).
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_CREATE_WITH_REQUIRED)

        dg.add_uint32(doId)
        dg.add_uint32(parentId)
        dg.add_uint32(zoneId)
        dg.add_uint16(dclass.get_number())

        packer = direct.DCPacker()
        for field in dclass.getFields():
            if field.isRequired() and field.getName() in fields:
                packer.beginPack(field)
                field.packArgs(packer, fields[field.getName()])
                packer.endPack()

        dg.appendData(packer.getDatagram())

        self.air.send(dg)

    def create_object_with_required_other(self, doId: int, parentId: int, zoneId: int, dclass: direct.DClass, fields: dict) -> None:
        """
        Create an object on the State Server, specifying its initial location as (parent_id, zone_id), its class, 
        and initial field data. The object then broadcasts an ENTER_LOCATION message to its location channel, 
        and sends a CHANGING_ZONE with old location (0,0) to its parent (if it has one).

        Additionally, the object sends a GET_LOCATION to its children over the parent messages channel (1 << 32|parent_id) with context 1001 (STATESERVER_CONTEXT_WAKE_CHILDREN).
        """  

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_CREATE_WITH_REQUIRED_OTHER)

        dg.add_uint32(doId)
        dg.add_uint32(parentId)
        dg.add_uint32(zoneId)
        dg.add_uint16(dclass.get_number())

        packer = direct.DCPacker()
        for field in dclass.getFields():
            if field.isRequired() and field.getName() in fields:
                packer.beginPack(field)
                field.packArgs(packer, fields[field.getName()])
                packer.endPack()

        dg.appendData(packer.getDatagram())

        self.air.send(dg)     

    def delete_ai_objects(self, channel: int) -> None:
        """
        Used by an AI Server to inform the State Server that it is going down. 
        The State Server will then delete all objects matching the ai_channel.

        The AI will typically hang this on its connected MD using ADD_POST_REMOVE, so that the message goes 
        out automatically if the AI loses connection unexpectedly.
        """

        dg = PyDatagram()
        dg.addServerHeader(self.air.serverId, channel, msgtypes.STATESERVER_DELETE_AI_OBJECTS)

        self.air.send(dg)

    deleteAIObjects = delete_ai_objects

    def get_object_field(self, doId: int, field: str, callback: object) -> None:
        """
        Get a single field from an object.
        You should already be sure the object actually exists, otherwise the
        callback will never be called.
        Callback is called as: callback(doId, field, value)
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_GET_FIELD)

        dg.add_uint32(ctx)
        dg.add_uint32(doId)
        dg.add_string(field)

        self.air.send(dg)

    getObjectField = get_object_field

    def handle_get_field_resp(self, di: object) -> None:
        """
        Handles STATESERVER_OBJECT_GET_FIELD_RESP messages
        """

        ctx         = di.get_uint32()
        doId        = di.get_uint32()
        field       = di.get_string()
        value       = di.get_string()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected STATESERVER_OBJECT_GET_FIELD_RESP (ctx: %d)' % ctx)
            return

        try:
            self.__callbacks[ctx](doId, field, value)
        finally:
            del self.__callbacks[ctx]

    def get_object_fields(self, doId: int, fields: list, callback: object) -> None:
        """
        Get multiple fields from an object.
        You should already be sure the object actually exists, otherwise the
        callback will never be called.
        Callback is called as: callback(doId, fields)
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_GET_FIELDS)

        dg.add_uint32(ctx)
        dg.add_uint32(doId)

        dg.add_uint16(len(fields))
        for field in fields:
            dg.add_string(field)

        self.air.send(dg)

    getObjectFields = get_object_fields

    def handle_get_fields_resp(self, di: object) -> None:
        """
        Handles STATESERVER_OBJECT_GET_FIELDS_RESP messages
        """

        ctx         = di.get_uint32()
        doId        = di.get_uint32()
        fields      = {}

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected STATESERVER_OBJECT_GET_FIELDS_RESP (ctx: %d)' % ctx)
            return

        count = di.get_uint16()
        for i in range(count):
            field = di.get_string()
            value = di.get_string()
            fields[field] = value

        try:
            self.__callbacks[ctx](doId, fields)
        finally:
            del self.__callbacks[ctx]

    def get_object(self, doId: int, callback: object) -> None:
        """
        Get the entire state of an object.
        You should already be sure the object actually exists, otherwise the
        callback will never be called.
        Callback is called as: callback(doId, parentId, zoneId, dclass, fields)
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_GET_ALL)
        dg.add_uint32(ctx)
        dg.add_uint32(doId)

        self.air.send(dg)

    def handle_get_object_resp(self, di: object) -> None:
        """
        Handles STATESERVER_OBJECT_GET_ALL_RESP messages
        """

        ctx         = di.get_uint32()
        doId        = di.get_uint32()
        parentId    = di.get_uint32()
        zoneId      = di.get_uint32()
        classId     = di.get_uint16()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected STATESERVER_OBJECT_GET_ALL_RESP (ctx: %d)' % ctx)
            return

        if classId not in self.air.dclassesByNumber:
            self.notify.warning('Received STATESERVER_OBJECT_GET_ALL_RESP for unknown dclass=%d! (Object %d)' % (classId, doId))
            return

        dclass = self.air.dclassesByNumber[classId]

        fields = {}
        unpacker = direct.DCPacker()
        unpacker.setUnpackData(di.getRemainingBytes())

        # Required:
        for i in range(dclass.getNumInheritedFields()):
            field = dclass.getInheritedField(i)
            if not field.isRequired() or field.asMolecularField(): continue
            unpacker.beginUnpack(field)
            fields[field.getName()] = field.unpackArgs(unpacker)
            unpacker.endUnpack()

        # Other:
        other = unpacker.rawUnpackUint16()
        for i in range(other):
            field = dclass.getFieldByIndex(unpacker.rawUnpackUint16())
            unpacker.beginUnpack(field)
            fields[field.getName()] = field.unpackArgs(unpacker)
            unpacker.endUnpack()

        try:
            self.__callbacks[ctx](doId, parentId, zoneId, dclass, fields)
        finally:
            del self.__callbacks[ctx]

    def set_object_field(self, doId: int, field: str, value: object) -> None:
        """
        Set a single field on an object.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_SET_FIELD)

        dg.add_uint32(doId)
        dg.add_string(field)
        dg.add_string(value)

        self.air.send(dg)

    setObjectField = set_object_field

    def set_object_fields(self, doId: int, fields: dict) -> None:
        """
        Set multiple fields on an object.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_SET_FIELDS)

        dg.add_uint32(doId)
        dg.add_uint16(len(fields))
        for field, value in fields.items():
            dg.add_string(field)
            dg.add_string(value)

        self.air.send(dg)

    setObjectFields = set_object_fields

    def delete_object_field(self, doId: int, field: str) -> None:
        """
        Delete a single field from an object.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_DELETE_FIELD)

        dg.add_uint32(doId)
        dg.add_string(field)

        self.air.send(dg)

    deleteObjectField = delete_object_field

    def delete_object_fields(self, doId: int, fields: list) -> None:
        """
        Delete multiple fields from an object.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_DELETE_FIELDS)

        dg.add_uint32(doId)
        dg.add_uint16(len(fields))
        for field in fields:
            dg.add_string(field)

        self.air.send(dg)

    deleteObjectFields = delete_object_fields

    def delete_object(self, doId: int) -> None:
        """
        Delete an object from the State Server.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_DELETE_RAM)

        dg.add_uint32(doId)

        self.air.send(dg)

    deleteObject = delete_object
    
    def set_location(self, do: object, parentId: int, zoneId: int) -> None:
        """
        Send a SET_LOCATION message to the State Server to move the object to
        the specified parentId/zoneId.
        """

        dg = PyDatagram()
        dg.addServerHeader(do.doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_SET_LOCATION)
        dg.add_uint32(parentId)
        dg.add_uint32(zoneId)

        self.air.send(dg)

    # Legacy methods for the original Panda3D Distributed Object implementation
    setLocation = set_location
    sendSetLocation = set_location

    def handle_obj_location(self, di: object) -> None:
        """
        Handles STATE_SERVER_OBJECT_CHANGING_LOCATION messages
        """
        
        doId        = di.get_uint32()
        parentId    = di.get_uint32()
        zoneId      = di.get_uint32()

        do = self.air.doId2do.get(doId)

        if not do:
            self.notify.warning('Received location for unknown doId=%d!' % (doId))
            return

        do.setLocation(parentId, zoneId)

    def handle_object_entry(self, di: object, other: bool) -> None:
        """
        Handles STATE_SERVER_OBJECT_ENTER_AI_WITH_REQUIRED and
        STATE_SERVER_OBJECT_ENTER_AI_WITH_REQUIRED_OTHER messages
        """

        doId        = di.get_uint32()
        parentId    = di.get_uint32()
        zoneId      = di.get_uint32()
        classId     = di.get_uint16()

        if classId not in self.air.dclassesByNumber:
            self.notify.warning('Received entry for unknown dclass=%d! (Object %d)' % (classId, doId))
            return

        if doId in self.air.doId2do:
            return # We already know about this object; ignore the entry.

        dclass = self.air.dclassesByNumber[classId]

        do = dclass.getClassDef()(self)
        do.dclass = dclass
        do.doId = doId

        # The DO came in off the server, so we do not unregister the channel when
        # it dies:
        do.doNotDeallocateChannel = True
        self.addDOToTables(do, location=(parentId, zoneId))

        # Now for generation:
        do.generate()
        if other:
            do.updateAllRequiredOtherFields(dclass, di)
        else:
            do.updateAllRequiredFields(dclass, di)

    def handle_object_exit(self, di: object) -> None:
        """
        Handles STATE_SERVER_OBJECT_CHANGING_AI and
        STATE_SERVER_OBJECT_DELETE_RAM messages
        """

        doId = di.get_uint32()
        if doId not in self.air.doId2do:
            self.notify.warning('Received AI exit for unknown object %d' % (doId))
            return

        do = self.air.doId2do[doId]
        self.removeDOFromTables(do)
        do.delete()
        do.sendDeleteEvent()

    def get_location(self, doId: int, callback: object) -> None:
        """
        Ask a DistributedObject where it is.
        You should already be sure the object actually exists, otherwise the
        callback will never be called.
        Callback is called as: callback(doId, parentId, zoneId)
        """

        ctx = self.air.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_GET_LOCATION)
        dg.add_uint32(ctx)

        self.air.send(dg)

    def handle_get_location_resp(self, di: object) -> None:
        """
        Handles STATESERVER_OBJECT_GET_LOCATION_RESP messages
        """

        ctx         = di.get_uint32()
        doId        = di.get_uint32()
        parentId    = di.get_uint32()
        zoneId      = di.get_uint32()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected STATESERVER_OBJECT_GET_LOCATION_RESP (ctx: %d)' % ctx)
            return

        try:
            self.__callbacks[ctx](doId, parentId, zoneId)
        finally:
            del self.__callbacks[ctx]

    def handle_get_activated_resp(self, di: object) -> None:
        """
        Handles DBSS_OBJECT_GET_ACTIVATED_RESP messages
        """

        ctx         = di.getUint32()
        doId        = di.getUint32()
        activated   = di.getUint8()

        if ctx not in self.__callbacks:
            self.notify.warning('Received unexpected DBSS_OBJECT_GET_ACTIVATED_RESP (ctx: %d)' %ctx)
            return

        try:
            self.__callbacks[ctx](doId, activated)
        finally:
            del self.__callbacks[ctx]

    def get_activated(self, doId: int, callback: object) -> None:
        """
        Ask the Database state server if a DistributedObject is activated. This will fire off
        a callback with the result.
        """

        ctx = self.get_context()
        self.__callbacks[ctx] = callback

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.DBSS_OBJECT_GET_ACTIVATED)
        dg.addUint32(ctx)
        dg.addUint32(doId)

        self.air.send(dg)


    def register_delete_ai_objects_post_remove(self, server_id :int) -> None:
        """
        Registers the delete_ai_objects method to be called when the AI disconnects.
        """

        dg = PyDatagram()
        dg.addServerHeader(server_id, self.air.ourChannel, msgtypes.STATESERVER_DELETE_AI_OBJECTS)

        dg.addChannel(self.air.ourChannel)
        self.air.add_post_remove(dg)

    registerDeleteAIObjectsPostRemove = register_delete_ai_objects_post_remove

    def request_delete(self, do: object) -> None:
        """
        Request the deletion of an object that already exists on the State Server.
        You should use do.requestDelete() instead. This is not meant to be
        called directly unless you really know what you are doing.
        """

        dg = PyDatagram()
        dg.addServerHeader(do.doId, self.ourChannel, msgtypes.STATESERVER_OBJECT_DELETE_RAM)
        dg.ad_uint32(do.doId)
        self.air.send(dg)

    requestDelete = request_delete


    def set_owner(self, doId: int, newOwner: int) -> None:
        """
        Sets the owner of a DistributedObject. This will enable the new owner to send "ownsend" fields,
        and will generate an OwnerView.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, self.air.ourChannel, msgtypes.STATESERVER_OBJECT_SET_OWNER)
        dg.add_uint64(newOwner)
        self.air.send(dg)

    setOwner = set_owner

    def set_ai(self, doId: int, aiChannel: int) -> None:
        """
        Sets the AI of the specified DistributedObjectAI to be the specified channel.
        Generally, you should not call this method, and instead call DistributedObjectAI.setAI.
        """

        dg = PyDatagram()
        dg.addServerHeader(doId, aiChannel, msgtypes.STATESERVER_OBJECT_SET_AI)
        dg.add_uint64(aiChannel)
        self.air.send(dg)

    setAI = set_ai

    def generate_with_required(self, do: object, parentId: int, zoneId: int, optionalFields: list = []) -> None:
        """
        Generate an object onto the State Server, choosing an ID from the pool.
        You should use do.generateWithRequired(...) instead. This is not meant
        to be called directly unless you really know what you are doing.
        """

        doId = self.air.allocate_channel()
        self.generate_with_required_and_id(do, doId, parentId, zoneId, optionalFields)

    generateWithRequired = generate_with_required

    def generate_with_required_and_id(self, do: object, doId: int, parentId: int, zoneId: int, optionalFields: list = []) -> None:
        """
        Generate an object onto the State Server, specifying its ID and location.
        You should use do.generateWithRequiredAndId(...) instead. This is not
        meant to be called directly unless you really know what you are doing.
        """

        do.doId = doId
        self.addDOToTables(do, location=(parentId, zoneId))
        do.sendGenerateWithRequired(self, parentId, zoneId, optionalFields)

    generateWithRequiredAndId = generate_with_required_and_id