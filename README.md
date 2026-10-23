# ROBO CTRL — browser remote for HC-05 Arduino robot

A local-only web UI with a directional pad, hold-to-drive controls, keyboard support, live distance display, activity log, and a Python serial/WebSocket bridge.

## Requirements

- Ubuntu/Linux laptop with Python 3
- HC-05 paired and mapped to a serial port (default `/dev/rfcomm0`)
- Arduino firmware that accepts `U`, `D`, `L`, `R`, `S`, `X` over Bluetooth and prints distance lines such as `Distance: 12 cm`
- Arduino's HC-05 software serial at 9600 baud

## Run

1. Pair/bind the HC-05 as you normally do. If needed, bind it to `/dev/rfcomm0` first.
2. Extract this folder.
3. In a terminal:

   ```bash
   cd robo_ctrl
   ./run.sh
   ```

   If your serial port is different, pass it as an argument, e.g. `./run.sh /dev/rfcomm1`.
4. Open `http://127.0.0.1:8080` in your browser.
5. Keep the terminal running. Use the on-screen directional pad or keyboard arrows/WASD. Direction controls are hold-to-drive: release to send `S`.

## Bluetooth serial port

If `/dev/rfcomm0` is not already bound, use your existing HC-05 pairing setup. A common Linux flow is `rfcomm bind 0 <HC-05-MAC> 1`, which requires the Bluetooth device to be paired and the RFCOMM channel to be correct. Do not run two programs that open the same serial port simultaneously; close the Bluetooth terminal app first.

Check available ports with:

```bash
ls -l /dev/rfcomm* /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

If permission is denied, check device permissions and your Linux serial-device group; do not run the GUI exposed to the network as root.

## Important behavior

- The UI only binds to `127.0.0.1` by default; it is not exposed to your LAN.
- The bridge sends `S` when the browser WebSocket disconnects and when the bridge shuts down, as a best-effort software stop.
- This is not a hardware emergency stop. Test with the wheels lifted first.
- The GUI parses distance output in the form `Distance: 12 cm`. If your Arduino prints a different label, update the regex in `index.html` or make the firmware use this format.
- Your Arduino firmware must send `Distance: ... cm` lines for the live display. In the current sketch, distance is printed while moving forward and when `X` is requested.
