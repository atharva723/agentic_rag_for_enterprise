# NovaRetail Store IT, NovaPOS, and Store Network

- Document ID: NR-IT-009
- Owner: Store IT
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Store employees and managers using NovaPOS

## Purpose

Use this guide to report NovaPOS failures, operate within offline limits, and check store card readers, receipt printers, and network connections safely.

## Report NovaPOS down as a P1 incident

NovaPOS down in a store is a P1 incident: call the Service Desk at `+1-555-0142` and press `1`. Use extension `4357` on a company phone.

1. Say that the store POS is down and describe whether one terminal or every terminal is affected.
2. Give the location, failure start time, exact error, and any available workaround.
3. State whether NovaPOS is completely unavailable or operating offline.
4. Record the ticket number and follow the Service Desk's instructions.

P1 phone support operates 24x7, with a 15-minute first response and a 4-hour target fix. The Service Desk routes store and POS investigation to Store IT. Do not wait for a portal or email reply before calling.

## Use NovaPOS offline mode within its limit

NovaPOS offline mode accepts cash and stored-value cards for up to 4 hours and declines card payments. The 4-hour period starts when NovaPOS enters offline mode during the outage.

1. Note the offline start time displayed by NovaPOS and tell the Service Desk.
2. Explain the available payment methods before starting a sale.
3. Accept only cash or stored-value cards while offline.
4. Do not retry declined card payments through another offline terminal.
5. Stop offline transactions at the 4-hour limit and call for instructions.

Restarting a terminal does not extend the outage's offline allowance. Keep the incident ticket open until normal service is verified. Offline capability is temporary; report the connection failure promptly and describe its impact.

## Check a NovaPOS card reader that is not working

A NovaPOS card reader failure should be checked against the terminal's connection state before retrying a payment. NovaPOS offline mode declines card payments even if the reader has power.

1. Check whether NovaPOS reports an offline connection.
2. If online, check the reader's power and visible cable connections without opening the device.
3. Note the exact reader or NovaPOS error.
4. Check the sale's recorded payment result before repeating any payment attempt.
5. If the result is unclear, stop retrying and contact the Service Desk.

Report whether other terminals have the same problem. Do not photograph card details, write down payment credentials, or install reader software. The Service Desk coordinates Store IT support.

## Clear a NovaPOS receipt printer problem

A NovaPOS receipt printer shown as offline or jammed should be checked without repeating the sale. A missing receipt does not prove that the payment failed.

1. Check printer power and the visible connection to the terminal.
2. Confirm that the correct paper is loaded and the cover is closed.
3. For a jam, pause printing and follow the printer's posted paper-clearing instructions.
4. Remove only loose paper that can be reached without tools; do not open internal mechanisms.
5. Recheck printer readiness and the sale record before requesting a receipt reprint.

If the jam or offline state continues, report the error and checks completed to the Service Desk. Do not create a second sale merely to obtain a receipt.

## Check a NovaRetail store network failure

A NovaRetail store network failure affecting NovaPOS requires a phone report, not repeated changes to terminal settings. If the whole store network or POS is down, call `+1-555-0142` and press `1`.

1. Check whether other terminals and company devices have lost their connection.
2. Check visible power and cables at the affected terminal without moving shared equipment.
3. For wireless company devices, confirm `NovaRetail-Staff`, not `NovaRetail-Guest`.
4. Tell the Service Desk whether NovaPOS is offline and when offline mode started.
5. Record the ticket number and follow Store IT's directed checks.

Do not connect POS to guest Wi-Fi or a phone hotspot, reset shared network equipment, or install an alternative network device. Guest Wi-Fi provides internet only.

## Frequently asked questions

**Q: The tills are down. Who do I call?**
A: NovaPOS down is P1. Call the NovaRetail Service Desk at `+1-555-0142` and press `1`; P1 support is available 24x7.

**Q: How long can we sell while offline?**
A: NovaPOS offline mode allows cash and stored-value cards for up to 4 hours from entering offline mode. Card payments are declined, and restarting a terminal does not extend the limit.

**Q: The card reader isn't working. What should I check?**
A: Check whether NovaPOS is offline, then reader power, connections, and the recorded payment result. Stop retries if payment status is unclear and contact the Service Desk.

**Q: The receipt printer is jammed. Should I redo the sale?**
A: Do not repeat a NovaPOS sale for a missing receipt. Check paper, power, connections, and posted jam-clearing instructions; verify the sale record before requesting a reprint.
