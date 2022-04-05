# -*- coding: utf-8 -*-

import asyncio, argparse, struct, signal
from bleak import BleakClient
from pylsl import StreamInfo, StreamOutlet


# long UUID for standard HR characteristic 
CHARACTERISTIC_UUID_HR = "00002a37-0000-1000-8000-00805f9b34fb"
# polar purple
ADDRESS = "A0:9E:1A:A8:B4:2F"

# how often we expect to get new data from device (Hz)
SAMPLINGRATE = 12

class BBeltBleak():
    """
    Experimeting with bleak and asyncio. 
    callback: function that will be called upon new samples, with a a list of samples in parameters
    FIXME: better useage of asyncio...
    """
    def __init__(self, addr, char_id, verbose=False, callback=None):
        """
        addr: MAC adresse
        char_id: GATT characteristic ID
        verbose: debug info to stdout
        """
        self.bamp = 0
        self.bIR = 0 # Note: we might not get additional infrared values
        self.addr = addr
        self.char_id = char_id
        self.samples_in = 0
        self.callback = callback
        self.client = BleakClient(self.addr) 

    def launch(self):
        """
        blocking call, connect and then wait for notifications
        """
        asyncio.run(self._main())

    def _ble_handler(self, sender, data):
        """
        Handler for incoming BLE Gatt data, update values, print if verbose
        """
        # might get 8 bytes, 4 for red led, 4 for IR led
        if (len(data) >= 4):
            self.bamp = struct.unpack('>L', data[0:4])[0]
            # got optionnal IR value, update it as well
            if (len(data) >= 8):
                self.bIR = struct.unpack('>L', data[4:8])[0]
            self.samples_in+=1

            if args.verbose :
                print("Breathing Amp: " + str(self.bamp) + " raw IR: " + str(self.bIR))

            if self.callback is not None:
                self.callback([self.bamp, self.bIR])

    async def connect(self):
        """
        Establish connection with breathing belt
        """
        if not self.client.is_connected:
            print("Connecting to %s" % self.addr)
            try:
                await self.client.connect()
                print(f"Connected: {self.client.is_connected}")
            except Exception as e:
                print(e)

    async def _main(self):
        await self.connect()
        # in the background HR values are handled by the callback function
        print("start notify")
        try:
            await self.client.start_notify(self.char_id, self._ble_handler)
            print("notify started")

            print("launch the loop")
            while True:
                # sleep used to debug sampling rate but also to make the script work in the background
                await asyncio.sleep(5)
                print("Samples incoming at: %s Hz" % (self.samples_in/5.))
                self.samples_in = 0
            
        except Exception as e:
            print(e)


    def process(self, delay):
        asyncio.sleep(delay)


    async def _terminate(self):
        await self.client.stop_notify(self.char_id)
        await self.client.disconnect()
        
    def terminate(self):
        """
        Gracefully end BLE connection
        FIXME: we should await...
        """
        try:
            asyncio.run(self._terminate())
        except Exception as e:
            print(e)
    

if __name__ == "__main__":
    # make sure to catch SIGINT and also catch SIGTERM signals with KeyboardInterrupt, to cleanup properly later
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)

    # retrieve MAC address
    parser = argparse.ArgumentParser(description='Stream breathing amplitude of bluetooth BLE compatible devices using LSL.')
    parser.add_argument("-m", "--mac-address", help="MAC address of the  device.", default="FB:88:11:1E:90:F3", type=str)
    parser.add_argument("-n", "--name", help="LSL id name on the network", default="ullo_bb", type=str)
    parser.add_argument("-t", "--type", help="LSL id type on the network", default="breathing_amp", type=str)
    parser.add_argument("-v", "--verbose", action='store_true', help="Print more verbose information.")

    parser.set_defaults()
    args = parser.parse_args()

    # characteristic where the belt sends raw values
    char_id = "0000fed1-0000-1000-8000-00805f9b34fb"    

    # init LSL streams
    info_bamp = StreamInfo(args.name, args.type, 2, SAMPLINGRATE, 'float32', '%s_%s_%s' % (args.name, args.type, args.mac_address))
    outlet_bamp = StreamOutlet(info_bamp)

    def stream(data):
        """
        will be called by bbelt
        TODO: check parameters (number, types)
        """
        outlet_bamp.push_sample(data)

    bbelt = BBeltBleak(args.mac_address, char_id, verbose = args.verbose, callback=stream)

    try:
        bbelt.launch()
    except KeyboardInterrupt:
        print("Catching Ctrl-C or SIGTERM, bye!")
    finally:
        # disconnected and erase outlet before letting be
        bbelt.terminate()
        del outlet_bamp
        print("terminated")
