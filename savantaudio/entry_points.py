"""
savantaudio.entry_points.py
~~~~~~~~~~~~~~~~~~~~~~

This module contains the entry-point functions for the savantaudio module,
that are referenced in setup.py.
"""

from os import remove
from sys import argv
import sys
import re

import asyncio
from . import client

def print_links(switch):
    print("Links:")
    for output, input in switch.links.items():
        print(f'{switch.input(input)} => {switch.output(output)}')

def print_peq(output):
    """Print PEQ band configuration for an output."""
    print(f"PEQ Configuration for Output {output.number}:")
    bands = output.get_all_peq_bands()
    for band_num, config in bands.items():
        print(f"  Band {band_num}: freq={config['frequency']}Hz, "
              f"level={config['level']}dB, q={config['q']}, "
              f"valid={config['valid']}")

def main() -> None:
    """Main package entry point.

    Delegates to other functions based on user input.
    """

    try:
        user_cmd = argv[1]
        if user_cmd == 'install':
            pass
        elif user_cmd == 'dump':
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            print(str(switch))
            for input in switch.inputs:
                print(str(input))
            for output in switch.outputs:
                print(str(output))
                print_peq(output)
            print_links(switch)
        elif user_cmd == 'link':
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            loop.run_until_complete(switch.link(int(argv[4]), int(argv[5])))
            print_links(switch)
        elif user_cmd == 'unlink':
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            loop.run_until_complete(switch.unlink(int(argv[4]), int(argv[5]) if len(argv) > 5 else None))
            print_links(switch)
        elif user_cmd == 'set-volume':
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            loop.run_until_complete(switch.output(int(argv[4])).set_volume(int(argv[5])))
            print(str(switch.output(int(argv[4]))))
        elif user_cmd == 'get-volume':
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            print(str(switch.output(int(argv[4])).volume))
        elif user_cmd == 'set-peq':
            # set-peq <host> <port> <output> <band> <frequency> <level> <q>
            # Example: savantaudio-client set-peq 192.168.1.216 8085 2 1 250 -3 2.0
            if len(argv) < 9:
                print("Usage: savantaudio-client set-peq <host> <port> <output> <band> <frequency> <level> <q>")
                print("Example: savantaudio-client set-peq 192.168.1.216 8085 2 1 250 -3 2.0")
                return
            
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            
            output_num = int(argv[4])
            band = int(argv[5])
            frequency = int(argv[6])
            level = int(argv[7])
            q = float(argv[8])
            
            loop.run_until_complete(
                switch.output(output_num).set_peq_band(band, frequency, level, q)
            )
            print_peq(switch.output(output_num))
            
        elif user_cmd == 'set-peq-freq':
            # set-peq-freq <host> <port> <output> <band> <frequency>
            # Example: savantaudio-client set-peq-freq 192.168.1.216 8085 2 1 250
            if len(argv) < 8:
                print("Usage: savantaudio-client set-peq-freq <host> <port> <output> <band> <frequency>")
                print("Example: savantaudio-client set-peq-freq 192.168.1.216 8085 2 1 250")
                return
            
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            
            output_num = int(argv[4])
            band = int(argv[5])
            frequency = int(argv[6])
            
            loop.run_until_complete(
                switch.output(output_num).set_peq_frequency(band, frequency)
            )
            band_config = switch.output(output_num).get_peq_band(band)
            print(f"Output {output_num} Band {band} frequency set to {band_config['frequency']}Hz")
            
        elif user_cmd == 'set-peq-level':
            # set-peq-level <host> <port> <output> <band> <level>
            # Example: savantaudio-client set-peq-level 192.168.1.216 8085 2 1 -3
            if len(argv) < 8:
                print("Usage: savantaudio-client set-peq-level <host> <port> <output> <band> <level>")
                print("Example: savantaudio-client set-peq-level 192.168.1.216 8085 2 1 -3")
                return
            
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            
            output_num = int(argv[4])
            band = int(argv[5])
            level = int(argv[6])
            
            loop.run_until_complete(
                switch.output(output_num).set_peq_level(band, level)
            )
            band_config = switch.output(output_num).get_peq_band(band)
            print(f"Output {output_num} Band {band} level set to {band_config['level']}dB")
            
        elif user_cmd == 'set-peq-q':
            # set-peq-q <host> <port> <output> <band> <q>
            # Example: savantaudio-client set-peq-q 192.168.1.216 8085 2 1 2.0
            if len(argv) < 8:
                print("Usage: savantaudio-client set-peq-q <host> <port> <output> <band> <q>")
                print("Example: savantaudio-client set-peq-q 192.168.1.216 8085 2 1 2.0")
                return
            
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            
            output_num = int(argv[4])
            band = int(argv[5])
            q = float(argv[6])
            
            loop.run_until_complete(
                switch.output(output_num).set_peq_q(band, q)
            )
            band_config = switch.output(output_num).get_peq_band(band)
            print(f"Output {output_num} Band {band} Q set to {band_config['q']}")
            
        elif user_cmd == 'get-peq':
            # get-peq <host> <port> <output> [band]
            # Example: savantaudio-client get-peq 192.168.1.216 8085 2
            # Example: savantaudio-client get-peq 192.168.1.216 8085 2 1
            if len(argv) < 5:
                print("Usage: savantaudio-client get-peq <host> <port> <output> [band]")
                print("Example: savantaudio-client get-peq 192.168.1.216 8085 2")
                print("Example: savantaudio-client get-peq 192.168.1.216 8085 2 1")
                return
            
            switch = client.Switch(host=argv[2], port=int(argv[3]))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(switch.connect())
            
            output_num = int(argv[4])
            
            if len(argv) > 5:
                # Get specific band
                band = int(argv[5])
                band_config = switch.output(output_num).get_peq_band(band)
                if band_config:
                    print(f"Output {output_num} Band {band}:")
                    print(f"  Frequency: {band_config['frequency']}Hz")
                    print(f"  Level: {band_config['level']}dB")
                    print(f"  Q: {band_config['q']}")
                    print(f"  Valid: {band_config['valid']}")
            else:
                # Get all bands
                print_peq(switch.output(output_num))
                
        else:
            print(f"Unknown command: {user_cmd}")
            print_help()
            
    except IndexError as e:
        print(f"Error: Missing arguments for command '{argv[1] if len(argv) > 1 else 'unknown'}'")
        print_help()
    except ValueError as e:
        print(f"Error: Invalid argument - {e}")
    except Exception as e:
        print(f"Error: {e}")
    
    return None

def print_help():
    """Print help message with all available commands."""
    help_text = """
Savant Audio Client - Command Line Interface

Usage: savantaudio-client <command> [arguments]

ROUTING COMMANDS:
  dump <host> <port>
    Show all inputs, outputs, links, and PEQ settings
    
  link <host> <port> <output> <input>
    Link an output to an input
    
  unlink <host> <port> <output> [input]
    Unlink an output from an input

VOLUME COMMANDS:
  set-volume <host> <port> <output> <level>
    Set output volume (-38 to 0 dB)
    Example: set-volume 192.168.1.216 8085 2 -20
    
  get-volume <host> <port> <output>
    Get output volume
    Example: get-volume 192.168.1.216 8085 2

PEQ (PARAMETRIC EQUALIZER) COMMANDS:
  set-peq <host> <port> <output> <band> <frequency> <level> <q>
    Set all PEQ parameters for a band (1-7)
    Frequency: 20-20000 Hz
    Level: -12 to +12 dB
    Q: 0.4041 to 7.2077
    Example: set-peq 192.168.1.216 8085 2 1 250 -3 2.0
    
  set-peq-freq <host> <port> <output> <band> <frequency>
    Set only the frequency for a PEQ band
    Example: set-peq-freq 192.168.1.216 8085 2 1 250
    
  set-peq-level <host> <port> <output> <band> <level>
    Set only the level for a PEQ band
    Example: set-peq-level 192.168.1.216 8085 2 1 -3
    
  set-peq-q <host> <port> <output> <band> <q>
    Set only the Q for a PEQ band
    Example: set-peq-q 192.168.1.216 8085 2 1 2.0
    
  get-peq <host> <port> <output> [band]
    Get PEQ settings (all bands or specific band)
    Example: get-peq 192.168.1.216 8085 2
    Example: get-peq 192.168.1.216 8085 2 1
"""
    print(help_text)

if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(main())
