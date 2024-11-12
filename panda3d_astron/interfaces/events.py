"""
"""

from direct.distributed.PyDatagram import PyDatagram
from panda3d import core as p3d
from panda3d_toolbox import runtime
import collections

# Helper functions for logging output:
def msgpack_length(dg, length, fix, maxfix, tag8, tag16, tag32):
    if length < maxfix:
        dg.addUint8(fix + length)
    elif tag8 is not None and length < 1<<8:
        dg.addUint8(tag8)
        dg.addUint8(length)
    elif tag16 is not None and length < 1<<16:
        dg.addUint8(tag16)
        dg.addBeUint16(length)
    elif tag32 is not None and length < 1<<32:
        dg.addUint8(tag32)
        dg.addBeUint32(length)
    else:
        raise ValueError('Value too big for MessagePack')

def msgpack_encode(dg, element):
    if element == None:
        dg.addUint8(0xc0)
    elif element is False:
        dg.addUint8(0xc2)
    elif element is True:
        dg.addUint8(0xc3)
    elif isinstance(element, int):
        if -32 <= element < 128:
            dg.addInt8(element)
        elif 128 <= element < 256:
            dg.addUint8(0xcc)
            dg.addUint8(element)
        elif 256 <= element < 65536:
            dg.addUint8(0xcd)
            dg.addBeUint16(element)
        elif 65536 <= element < (1<<32):
            dg.addUint8(0xce)
            dg.addBeUint32(element)
        elif (1<<32) <= element < (1<<64):
            dg.addUint8(0xcf)
            dg.addBeUint64(element)
        elif -128 <= element < -32:
            dg.addUint8(0xd0)
            dg.addInt8(element)
        elif -32768 <= element < -128:
            dg.addUint8(0xd1)
            dg.addBeInt16(element)
        elif -1<<31 <= element < -32768:
            dg.addUint8(0xd2)
            dg.addBeInt32(element)
        elif -1<<63 <= element < -1<<31:
            dg.addUint8(0xd3)
            dg.addBeInt64(element)
        else:
            raise ValueError('int out of range for msgpack: %d' % element)
    elif isinstance(element, dict):
        msgpack_length(dg, len(element), 0x80, 0x10, None, 0xde, 0xdf)
        for k,v in list(element.items()):
            msgpack_encode(dg, k)
            msgpack_encode(dg, v)
    elif isinstance(element, list):
        msgpack_length(dg, len(element), 0x90, 0x10, None, 0xdc, 0xdd)
        for v in element:
            msgpack_encode(dg, v)
    elif isinstance(element, str):
        # 0xd9 is str 8 in all recent versions of the MsgPack spec, but somehow
        # Logstash bundles a MsgPack implementation SO OLD that this isn't
        # handled correctly so this function avoids it too
        msgpack_length(dg, len(element), 0xa0, 0x20, None, 0xda, 0xdb)
        dg.appendData(element.encode('utf-8'))
    elif isinstance(element, float):
        # Python does not distinguish between floats and doubles, so we send
        # everything as a double in MsgPack:
        dg.addUint8(0xcb)
        dg.addBeFloat64(element)
    else:
        raise TypeError('Encountered non-MsgPack-packable value: %r' % element)

class EventLoggerInterface(object):
    """
    This class provides a simple interface for logging events to the central
    Event Logger. It is intended to be used by the AI and UberDOG to log events
    that are of interest to the game as a whole. The Event Logger is a separate
    server that listens for event messages and logs them to a central database.
    """

    def __init__(self, air: object):
        """
        Initialize the Event Logger interface. This will set up the necessary
        network connections to the Event Logger server, if one is configured.
        """

        self.air = air
        self.eventLogId = runtime.config.GetString('eventlog-id', 'AIR:%d' % self.air.ourChannel)
        self.eventSocket = None

        eventLogHost = runtime.config.GetString('eventlog-host', '')
        if eventLogHost:
            if ':' in eventLogHost:
                host, port = eventLogHost.split(':', 1)
                self.setEventLogHost(host, int(port))
            else:
                self.setEventLogHost(eventLogHost)

    @property
    def notify(self) -> object:
        """
        Retrieves the parent repositories notify object
        """

        return self.air.notify

    def setEventLogHost(self, host, port=7197):
        """
        Set the target host for Event Logger messaging. This should be pointed
        at the UDP IP:port that hosts the cluster's running Event Logger.
        Providing a value of None or an empty string for 'host' will disable
        event logging.
        """

        if not host:
            self.eventSocket = None
            return

        address = p3d.SocketAddress()
        if not address.setHost(host, port):
            self.notify.warning('Invalid Event Log host specified: %s:%s' % (host, port))
            self.eventSocket = None
        else:
            self.eventSocket = p3d.SocketUDPOutgoing()
            self.eventSocket.InitToAddress(address)

    set_event_log_host = setEventLogHost

    def writeServerEvent(self, logtype, *args, **kwargs):
        """
        Write an event to the central Event Logger, if one is configured.
        The purpose of the Event Logger is to keep a game-wide record of all
        interesting in-game events that take place. Therefore, this function
        should be used whenever such an interesting in-game event occurs.
        """

        if self.eventSocket is not None:
            return # No event logger configured!

        log = collections.OrderedDict()
        log['type'] = logtype
        log['sender'] = self.eventLogId

        for i,v in enumerate(args):
            # +1 because the logtype was _0, so we start at _1
            log['_%d' % (i+1)] = v

        log.update(kwargs)

        dg = PyDatagram()
        msgpack_encode(dg, log)
        self.eventSocket.Send(dg.getMessage())

    write_server_event = writeServerEvent