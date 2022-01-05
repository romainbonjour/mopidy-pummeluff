'''
Python module for the dedicated Mopidy Pummeluff threads.
'''

__all__ = (
    'TagReader',
)

from threading import Thread
from time import time
from logging import getLogger

import RPi.GPIO as GPIO
from rdm6300

from mopidy_pummeluff.registry import REGISTRY
from mopidy_pummeluff.actions.base import Action
from mopidy_pummeluff.sound import play_sound

LOGGER = getLogger(__name__)

class RFID(rdm6300.BaseReader):
    def card_inserted(self, card):
        print(f"card inserted {card}")
        '''
        Handle the scanned tag / retreived UID.

        :param str uid: The UID
        '''
        uid=card
        try:
            action = REGISTRY[str(uid)]
            LOGGER.info('Triggering action of registered tag')
            play_sound('success.wav')
            action(self.core)

        except KeyError:
            LOGGER.info('Tag is not registered, thus doing nothing')
            play_sound('fail.wav')
            action = Action(uid=uid)

        action.scanned   = time()
        TagReader.latest = action

    def card_removed(self, card):
        print(f"card removed {card}")

    def invalid_card(self, card):
        print(f"invalid card {card}")

class ReadError(Exception):
    '''
    Exception which is thrown when an RFID read error occurs.
    '''

class TagReader(Thread):
    '''
    Thread which reads RFID tags from the RFID reader.

    Because the RFID reader algorithm is reacting to an IRQ (interrupt), it is
    blocking as long as no tag is touched, even when Mopidy is exiting. Thus,
    we're running the thread as daemon thread, which means it's exiting at the
    same moment as the main thread (aka Mopidy core) is exiting.
    '''
    daemon = True
    latest = None

    def __init__(self, core, stop_event):
        '''
        Class constructor.

        :param mopidy.core.Core core: The mopidy core instance
        :param threading.Event stop_event: The stop event
        '''
        super().__init__()
        self.core       = core
        self.stop_event = stop_event
        self.rfid       = RFID('/dev/ttyS0')

    def run(self):
        '''
        Run RFID reading loop.
        '''
        rfid      = self.rfid

        while not rfid.stop_event.is_set():
            received_bytes = rfid.serial.read()
            if received_bytes and len(received_bytes) > 0:
                recieved_byte = received_bytes[0]
                assert len(received_bytes) == 1

                if recieved_byte == BaseReader._RFID_STARTCODE:
                    if len(rfid.current_fragment) > 0:
                        rfid._process_fragment(rfid.current_fragment)
                        rfid.current_fragment = []
                elif recieved_byte == BaseReader._RFID_ENDCODE:
                    if len(rfid.current_fragment) > 0:
                        rfid._process_fragment(rfid.current_fragment)
                        rfid.current_fragment = []
                else:
                    try:
                        fragment = int(received_bytes.decode('ascii'), 16)
                        rfid.current_fragment.append(fragment)

                    except ValueError:
                        logging.warning("[{port}] got trash resetting rfid read to assume we are at the begining".format(port=rfid.port))
                        rfid.current_fragment = []

            rfid._process_heartbeat()
            rfid.tick()

        rfid.close()
        GPIO.cleanup()  # pylint: disable=no-member

