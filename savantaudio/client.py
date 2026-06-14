"""
savantaudio.client.py
~~~~~~~~~~~~~~~~

Client class to interact with Savant Audio switch
"""

import abc
import asyncio
from dataclasses import dataclass
from genericpath import exists
from operator import truediv
from typing import Dict, Optional, Sequence, Tuple, TypeVar
from enum import Enum
from xmlrpc.client import Boolean
import re
import logging
import datetime

_LOGGER = logging.getLogger(__name__)

class Model(Enum):
    SSA_3220 = 'SSA-3200'
    SSA_3220D = 'SSA-3220D'

class Connection:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._writer = None
        self._lock = asyncio.Lock()
    
    async def connect(self):
        async with self._lock:
            await self._connect()

    async def _connect(self):
        if self._writer is None:
            _LOGGER.debug(f'Opening Connection to {self._host}:{self._port}')
            self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
            self._ts = datetime.datetime.now()

    async def close(self):
        async with self._lock:
            await self._close()

    async def _close(self):
        if self._writer is not None:
            _LOGGER.debug(f'Closing Connection to {self._host}:{self._port}')
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except:
                pass #ignore
            self._writer = None

    def reader(self):
        return self._reader
    
    @property
    def writer(self):
        return self._writer
    
    async def send(self, command: str) -> str:
        while True:
            try:
                async with self._lock:
                    if self._writer is None:
                        await self._connect() # already holding lock
                    self._ts = datetime.datetime.now()
                    self._writer.write(command.encode("ASCII") + b"\r\n")
                    await self._writer.drain()
                    data = await self._reader.readline()
                    response = data.decode().strip()
                    if len(response) > 0: 
                        yield response
                    else:
                        _LOGGER.debug(f'Failed to get response to {command}. Retrying')
                        await self._close() # already holding lock
                        continue
                    while True:
                        data = await self._reader.readline()
                        response = data.decode().strip()
                        if len(response) > 0: 
                            yield response
                        else:
                            return
            except ConnectionResetError as cre:
                _LOGGER.debug(f'Connection reset: {cre}')
                await self.close()
            except Exception as ex:
                _LOGGER.exception(f'Connection got exception: {ex}', exc_info=ex)
                await self.close()
                raise
    
    def check(self):
        return self._writer.is_closing()


class Input:
    def __init__(self, switch, number: int, name: str):
        self._switch = switch
        self._number = number
        self._name = name
        self._coaxial = True
        self._trim = 0
        self._valid = False
    
    @property
    def number(self):
        return self._number
    
    @property
    def name(self):
        return self._name
    
    @property
    def coaxial(self):
        return self._coaxial
    
    @property
    def valid(self):
        return self._valid
    
    @property
    def trim(self):
        return self._trim
    
    def __str__(self):
        return f'Input_{self._number}{{{{"Coaxial" if self._coaxial else "TOSLINK"}, trim={self._trim}dB}}'
       
    async def updated(self):
        _LOGGER.info(f'Output {self._number} Updated: {self}')
        await self._switch._updated("input-updated", self)

    async def parse(self, key: str, value: str):
        if key == 'trim':
            if self._trim != int(value[:-2]):
                self._trim = int(value[:-2])
                await self.updated()
            self._valid = True
        elif key == 'conf':
            if self._coaxial != (value == 'coaxial'):
                self._coaxial = value == 'coaxial'
                await self.updated()
        return True
        
    async def set_trim(self, trim: int):
        await self._switch.send_command(f'ainput-trim-set{self._number}:{trim}')
        pass
    
    async def set_coaxial(self, coax: bool):
        await self._switch.send_command(f'ainput-conf-set{self._number}:{"coaxial" if coax else "toslink"}')
        pass

    async def refresh(self):
        await self._switch.send_command(f'ainput-trim-get{self._number}')
        await self._switch.send_command(f'ainput-conf-get{self._number}')
        

class Output:
    def __init__(self, switch, number: int, name: str):
        self._switch = switch
        self._number = number
        self._name = name
        self._stereo = True
        self._passthru = False
        self._volume = 0
        self._mute = False
        self._delay = [0, 0]
        self._valid = False
        
        # PEQ state cache - 7 bands with frequency, level, q
        # Format: {band_number: {'frequency': int, 'level': int, 'q': float, 'valid': bool}}
        self._peq_bands = {}
        for band in range(1, 8):
            self._peq_bands[band] = {
                'frequency': 125,
                'level': 0,
                'q': 1.414,
                'valid': False
            }
    
    @property
    def number(self) -> int:
        return self._number
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def mute(self) -> bool:
        return self._mute
    
    @property
    def stereo(self) -> bool:
        return self._stereo
    
    @property
    def passthru(self) -> bool:
        return self._passthru
    
    @property
    def volume(self) -> int:
        return self._volume
    
    @property
    def delay(self) -> tuple:
        return self._delay
       
    def __str__(self):
        return f'Output_{self._number}{{{{"Stereo" if self._stereo else "Mono"}, {"Passthru" if self._passthru else "Processed"}, volume={self._volume}dB, delay={self._delay[0]}/{self._delay[1]}ms}}'
   
    async def updated(self):
        _LOGGER.info(f'Output {self._number} Updated: {self}')
        await self._switch._updated("output-updated", self)

    async def parse(self, key: str, value: str):
        _LOGGER.debug(f"Output.parse({key} => {value})")
        if key == 'vol':
            self._volume = int(value[:-2])
            self._valid = True
        elif key == 'mute':
            self._mute = (value == 'on')
        elif key == 'conf':
            self._passthru = (value == 'passthru')
        elif key == 'mono':
            self._stereo = (value == 'off')
        elif key == 'delayleft':
            self._delay[0] = int(value[:-2])
        elif key == 'delayright':
            self._delay[1] = int(value[:-2])
        return True

    async def refresh(self):
        _LOGGER.debug("Output[%d].refresh", self._number)
        await self._switch.send_command(f'aoutput-vol-get{self._number}')
        await self._switch.send_command(f'aoutput-conf-get{self._number}')
        await self._switch.send_command(f'aoutput-mute-get{self._number}')
        await self._switch.send_command(f'aoutput-mono-get{self._number}')
        if self._number < 17 and self._switch._model == Model.SSA_3220D:
            await self._switch.send_command(f'aoutput-delayboth-get{self._number}')
        # Refresh all PEQ band settings
        await self.refresh_peq()
    
    async def set_volume(self, vol: int):
        if vol < -38 or vol > 0:
            raise ValueError(f'Invalid volume level: {vol}dB')
        await self._switch.send_command(f'aoutput-vol-set{self._number}:{vol}dB')
        pass
    
    async def set_mute(self, mute: bool):
        await self._switch.send_command(f'aoutput-mute-set{self._number}:{"on" if mute else "off"}')
        pass
    
    async def set_mono(self, mono: bool):
        await self._switch.send_command(f'aoutput-mono-set{self._number}:{"on" if mono else "off"}')
        pass
    
    async def set_passthru(self, passthru: bool):
        await self._switch.send_command(f'aoutput-conf-set{self._number}:{"passthru" if passthru else "processed"}')
        pass
    
    async def set_delay(self, left: int, right: int):
        await self._switch.send_command(f'aoutput-delayleft-set{self._number}:{left}')
        await self._switch.send_command(f'aoutput-delayrighy-set{self._number}:{right}')
        pass
    
    # ===== PEQ (Parametric Equalizer) Methods =====
    
    async def refresh_peq(self):
        """Refresh all PEQ band settings from the device (all 7 bands)."""
        _LOGGER.debug(f"Output[{self._number}].refresh_peq")
        for band in range(1, 8):
            await self._switch.send_command(f'peqget-output{self._number}-band{band}')
    
    async def set_peq_band(self, band: int, frequency: int, level: int, q: float):
        """
        Set all PEQ parameters for a specific band (frequency, level, Q).
        
        This must be called before sending individual frequency/level/q commands.
        
        Args:
            band: Band number (1-7)
            frequency: Frequency in Hz (20-20000)
            level: Level in dB (-12 to +12)
            q: Q factor (0.4041 to 7.2077)
        
        Raises:
            ValueError: If parameters are out of valid range
        """
        if not 1 <= band <= 7:
            raise ValueError(f'Band must be between 1 and 7, got {band}')
        if not 20 <= frequency <= 20000:
            raise ValueError(f'Frequency must be between 20 and 20000 Hz, got {frequency}')
        if not -12 <= level <= 12:
            raise ValueError(f'Level must be between -12 and +12 dB, got {level}')
        if not 0.4041 <= q <= 7.2077:
            raise ValueError(f'Q must be between 0.4041 and 7.2077, got {q}')
        
        command = f'peqset-output{self._number}-band{band}:freq{frequency}-level{level}-q{q}'
        await self._switch.send_command(command)
        
        # Update cache
        self._peq_bands[band] = {
            'frequency': frequency,
            'level': level,
            'q': q,
            'valid': True
        }
    
    async def set_peq_frequency(self, band: int, frequency: int):
        """
        Set frequency for a specific PEQ band.
        
        Note: set_peq_band() must be called first for this band.
        
        Args:
            band: Band number (1-7)
            frequency: Frequency in Hz (20-20000)
        
        Raises:
            ValueError: If parameters are out of valid range
        """
        if not 1 <= band <= 7:
            raise ValueError(f'Band must be between 1 and 7, got {band}')
        if not 20 <= frequency <= 20000:
            raise ValueError(f'Frequency must be between 20 and 20000 Hz, got {frequency}')
        
        command = f'peqfreqset-output{self._number}-band{band}:{frequency}'
        await self._switch.send_command(command)
        
        # Update cache
        self._peq_bands[band]['frequency'] = frequency
        self._peq_bands[band]['valid'] = True
    
    async def set_peq_level(self, band: int, level: int):
        """
        Set level (dB) for a specific PEQ band.
        
        Note: set_peq_band() must be called first for this band.
        
        Args:
            band: Band number (1-7)
            level: Level in dB (-12 to +12)
        
        Raises:
            ValueError: If parameters are out of valid range
        """
        if not 1 <= band <= 7:
            raise ValueError(f'Band must be between 1 and 7, got {band}')
        if not -12 <= level <= 12:
            raise ValueError(f'Level must be between -12 and +12 dB, got {level}')
        
        command = f'peqlevelset-output{self._number}-band{band}:{level}'
        await self._switch.send_command(command)
        
        # Update cache
        self._peq_bands[band]['level'] = level
        self._peq_bands[band]['valid'] = True
    
    async def set_peq_q(self, band: int, q: float):
        """
        Set Q (bandwidth) for a specific PEQ band.
        
        Note: set_peq_band() must be called first for this band.
        
        Args:
            band: Band number (1-7)
            q: Q factor (0.4041 to 7.2077)
        
        Raises:
            ValueError: If parameters are out of valid range
        """
        if not 1 <= band <= 7:
            raise ValueError(f'Band must be between 1 and 7, got {band}')
        if not 0.4041 <= q <= 7.2077:
            raise ValueError(f'Q must be between 0.4041 and 7.2077, got {q}')
        
        command = f'peqqset-output{self._number}-band{band}:{q}'
        await self._switch.send_command(command)
        
        # Update cache
        self._peq_bands[band]['q'] = q
        self._peq_bands[band]['valid'] = True
    
    def get_peq_band(self, band: int) -> Optional[Dict]:
        """
        Get cached PEQ band configuration.
        
        Args:
            band: Band number (1-7)
        
        Returns:
            Dictionary with 'frequency', 'level', 'q', and 'valid' keys, or None if invalid band
        """
        if 1 <= band <= 7:
            return self._peq_bands[band].copy()
        return None
    
    def get_all_peq_bands(self) -> Dict:
        """
        Get all cached PEQ band configurations.
        
        Returns:
            Dictionary mapping band numbers (1-7) to their configurations
        """
        return {band: config.copy() for band, config in self._peq_bands.items()}
    
    async def parse_peq(self, band: int, value: str) -> bool:
        """
        Parse PEQ response from device and update cache.
        
        Format: freq125Hz-level5dB-q1.414
        Example response: peqget-output2-band2:freq125Hz-level-10dB-q1
        
        Args:
            band: Band number extracted from response
            value: The value string from response
        
        Returns:
            bool: True if parsing was successful
        """
        try:
            if not 1 <= band <= 7:
                return False
            
            # Parse frequency: freq125Hz
            freq_match = re.search(r'freq(\d+)Hz', value)
            if not freq_match:
                return False
            frequency = int(freq_match.group(1))
            
            # Parse level: level-10dB or level5dB
            level_match = re.search(r'level(-?\d+)dB', value)
            if not level_match:
                return False
            level = int(level_match.group(1))
            
            # Parse Q: q1.414 or q1
            q_match = re.search(r'q([\d.]+)$', value)
            if not q_match:
                return False
            q = float(q_match.group(1))
            
            # Validate ranges
            if not (20 <= frequency <= 20000):
                _LOGGER.warning(f"PEQ frequency out of range: {frequency}")
                return False
            if not (-12 <= level <= 12):
                _LOGGER.warning(f"PEQ level out of range: {level}")
                return False
            if not (0.4041 <= q <= 7.2077):
                _LOGGER.warning(f"PEQ Q out of range: {q}")
                return False
            
            # Update cache
            old_config = self._peq_bands[band]
            self._peq_bands[band] = {
                'frequency': frequency,
                'level': level,
                'q': q,
                'valid': True
            }
            
            # Log if changed
            if (old_config['frequency'] != frequency or 
                old_config['level'] != level or 
                old_config['q'] != q):
                _LOGGER.debug(f"Output[{self._number}] Band {band} updated: "
                             f"freq={frequency}Hz, level={level}dB, q={q}")
                await self._switch._updated("peq-updated", 
                                           (self._number, band, self._peq_bands[band].copy()))
            
            return True
        except (ValueError, AttributeError) as ex:
            _LOGGER.warning(f"Failed to parse PEQ response for band {band}: {ex}")
            return False


class Switch:
    """Class for connecting to switch

    """

    def __init__(self, host: str, port: int, model = Model.SSA_3220D) -> None:
        self._host = host
        self._port = port
        self._inputs = []
        self._outputs = []
        self._links = {} # output -> input
        self._callback = None
        self._connection = Connection(self._host, self._port)
        self._attributes = {}
        self._ready = False
        self._model = model
        if self._model == Model.SSA_3220 or self._model == Model.SSA_3220D:
            self._ninputs = 32
            self._noutputs = 20
        else:
            raise ValueError(f'Unknown model: {self._model}')
    
    @property
    def host(self):
        return self._host
    
    @property
    def port(self):
        return self._port
    
    @property
    def attributes(self):
        return self._attributes
    
    @property
    def model(self):
        return self._model
    
    async def connect(self):
        _LOGGER.debug("Connecting to Savant Audio Switch %s:%d", self._host, self._port)
        await self.refresh()
    
    def add_callback(self, callback):
        if self._callback is None:
            self._callback = callback
        else:
            cb = self._callback
            async def _cb(event: str, object):
                await cb(event, object)
                await callback(event, object)
            self._callback = _cb
    
    def __str__(self):
        return f"{{ host: {self._host}, port: {self._port}, attributes: {self._attributes}, inputs: {self._ninputs}, outputs: {self._noutputs}, links: {self._links} }}"
    
    async def _updated(self, event: str, object):
        if self._callback is not None:
            await self._callback(event, object)
    
    async def send_command(self, command: str):
        try:
            _LOGGER.debug(f"send_command: command='{command}'")
            async for reply in self._connection.send(command):
                _LOGGER.debug(f"send_command: reply='{reply}'")
                await self.parse(reply)
        except Exception as ex:
            _LOGGER.exception(f"Got exception {ex}")
            raise

    async def refresh_link(self, output: int):
        await self.send_command(f'switch-get{output}')

    async def get_link(self, output: int):
        await self.refresh_link(output)
        if output in self._links:
            return self._links[output]
        else:
            return None

    async def refresh(self):
        _LOGGER.debug("Switch.refresh %s:%d", self._host, self._port)
        async for reply in self._connection.send('fwrev'):
            m = re.search('fwrevPrimary; (.*)', reply)
            if m:
                self._attributes['fwrev'] = m.group(1)

        async for reply in self._connection.send('fpga-rev'):
            m = re.search('fpga-rev(.*)', reply)
            if m:
                self._attributes['fpgarev'] = m.group(1)
        
        async for reply in self._connection.send('status'):
            m = re.search('statusAPI1.0; (.*)', reply)
            if m:
                for part in m.group(1).split(';'):
                    part = part.strip()
                    if part.startswith('pn'):
                        self._attributes['pn'] = part
                    elif part.startswith('sn'):
                        self._attributes['sn'] = part
                    elif part.startswith('rev'):
                        self._attributes['rev'] = part
                    elif part == 'ready=yes':
                        self._ready = True
                    elif part == 'ready=no':
                        self._ready = False
                    elif part == 'Standalone-Audio-Switch-With-Delay':
                        self._model = Model.SSA_3220D
                    elif part == 'Standalone-Audio-Switch':
                        self._model = Model.SSA_3220


        for c in range(1, self._noutputs):
            await self.refresh_link(c)

        for i in range(1, self._ninputs+1):
            await self.input(i).refresh()

        for o in range(1, self._noutputs+1):
            await self.output(o).refresh()

    def input(self, num: int):
        while len(self._inputs) <= num:
            self._inputs.append(None)
        if self._inputs[num] is None:
            self._inputs[num] = Input(self, num, f'Input {num}')
        return self._inputs[num]

    def output(self, num: int):
        while len(self._outputs) <= num:
            self._outputs.append(None)
        if self._outputs[num] is None:
            self._outputs[num] = Output(self, num, f'Output {num}')
        return self._outputs[num]

    @property
    def inputs(self):
        return [input for input in self._inputs if input is not None]

    @property
    def outputs(self):
        return [output for output in self._outputs if output is not None]

    async def link(self, output: int, input: int):
        await self.send_command(f'switch-set{output}.{input}')

    async def unlink(self, output: int, input: int = None):
        if input is None:
            #unlink no matter what
            await self.send_command(f'switch-set{output}.disconnect')
        else:
            link = await self.get_link(output)
            if link is not None and link == input:
                await self.send_command(f'switch-set{output}.disconnect')

    async def link_changed(self, output: int, input: int):
        _LOGGER.info(f'switch {output} connected to {input}')
        await self._updated('link-changed', (output, input))
    
    @property
    def links(self):
        return self._links

    async def parse(self, value: str):
        if value.startswith('err'):
            return False
        
        # Check for PEQ responses: peqget-outputY-bandZ:...
        m = re.search(r'peqget-output(\d+)-band(\d+):(.*)', value)
        if m:
            output_num = int(m.group(1))
            band_num = int(m.group(2))
            band_value = m.group(3)
            await self.output(output_num).parse_peq(band_num, band_value)
            return True
        
        # Standard ainput/aoutput responses
        m = re.search(r'(ainput|aoutput)-([a-z\-]+)(\d+):(.*)', value)
        if m:
            if m.group(1) == 'ainput':
                await self.input(int(m.group(3))).parse(m.group(2), m.group(4))
            elif m.group(1) == 'aoutput':
                await self.output(int(m.group(3))).parse(m.group(2), m.group(4))
            else:
                raise ValueError(f'got unknown response: {value}')
        else:
            m = re.search(r'switch(\d+).(\d+)', value)
            if m:
                output = int(m.group(1))
                input = int(m.group(2))
                if input == 0:
                    if output in self._links:
                        del self._links[output]
                        await self.link_changed(output, input)
                else:
                    if output not in self._links or self._links[output] != input:
                        self._links[output] = input
                        await self.link_changed(output, input)
            else:
                raise ValueError(f'got unknown response: {value}')
        return True
