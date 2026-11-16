# NovaRetail Wi-Fi and Office Network

- Document ID: NR-IT-007
- Owner: Service Desk
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Employees using networks at HQ, distribution centers, and stores

## Purpose

Use this guide to choose NovaRetail Wi-Fi, reconnect a company device, and check slow wireless or wired connections without changing network equipment.

## Choose the correct NovaRetail Wi-Fi network

NovaRetail Wi-Fi uses the same network names at HQ, both DCs, and stores: `NovaRetail-Staff` for company devices and `NovaRetail-Guest` for visitors, customers, and personal devices.

- Connect company laptops and managed company phones to `NovaRetail-Staff`.
- Staff Wi-Fi uses preconfigured company-device certificate authentication, not a shared Wi-Fi password.
- Personal phones must not join `NovaRetail-Staff`.
- Guest Wi-Fi provides internet only, with no access to internal company systems.
- Personal-phone work use remains limited to Authenticator, Outlook, and Teams under app protection.

If a company device unexpectedly asks for a staff Wi-Fi password, contact the Service Desk. Do not borrow another employee's credentials or use an unofficial network with a similar name.

## Reconnect a company device to NovaRetail staff Wi-Fi

To reconnect a company device to `NovaRetail-Staff`, use the device's wireless network controls without changing its certificate or installing a new network profile.

1. Check that Wi-Fi is enabled and airplane mode is off.
2. Select `NovaRetail-Staff` and allow the company-device authentication to complete.
3. If the connection fails, disconnect and reconnect once.
4. If failure continues, forget the saved network through the device's network settings, then select `NovaRetail-Staff` again.
5. Restart the device after saving work if it still cannot connect.

If the staff network or certificate is unavailable, submit a ticket at `https://itportal.novaretail.example`. Include the device type, location, network name, and exact error; do not install certificates from messages.

## Give visitors and personal phones guest internet

NovaRetail guest internet is provided through `NovaRetail-Guest` at HQ, DCs, and stores. Visitors, customers, and employees' personal phones use this network instead of staff Wi-Fi.

1. Select `NovaRetail-Guest` using the device's Wi-Fi controls.
2. Open a browser if the guest welcome page does not appear.
3. Accept the displayed network-use terms to obtain internet access.
4. Do not enter a NovaRetail password or MFA code into the guest page.

Guest Wi-Fi needs no company account and cannot reach internal systems. A personal phone on guest Wi-Fi can use approved protected work apps, but cannot use NovaConnect VPN. Report a guest page demanding company credentials to `security@novaretail.example`.

## Connect a company device to an office wired port

NovaRetail office wired ports are for company devices on approved network connections. A wired connection is a useful check when company Wi-Fi is slow or unreliable.

1. Use an approved company laptop, docking station, and network cable.
2. Connect to the assigned desk port and check that the cable is seated.
3. Confirm that the device detects a wired network connection.
4. Try opening the company system needed for your work.
5. If no connection appears, report the desk or port location to the Service Desk.

Do not connect personal computers, routers, or wireless extenders to company ports. Do not move POS network cables or unplug shared network equipment to test an office connection.

## Troubleshoot slow NovaRetail office Wi-Fi

Slow NovaRetail office Wi-Fi should be checked for location, device, and business impact before reporting it as a whole-site network failure.

1. Confirm that the company device is on `NovaRetail-Staff`, not guest Wi-Fi.
2. Move to an open work area away from enclosed storage or thick walls.
3. Pause large, nonessential file transfers and test the affected task again.
4. Disconnect and reconnect Wi-Fi once; save work before restarting the device.
5. Try the assigned wired desk connection if available.
6. Ask whether nearby colleagues have the same problem.

Report the location, time, affected task, and number of affected users at `https://itportal.novaretail.example`. If the whole location is down or many users are blocked, call `+1-555-0142` for P1 support.

## Frequently asked questions

**Q: Which Wi-Fi should my work laptop use?**
A: Company devices use `NovaRetail-Staff` at HQ, DCs, and stores. NovaRetail staff Wi-Fi authenticates preconfigured company devices by certificate.

**Q: Can my personal phone use staff Wi-Fi?**
A: Personal phones must use `NovaRetail-Guest`, not `NovaRetail-Staff`. Protected work use is limited to Authenticator, Outlook, and Teams.

**Q: Office Wi-Fi is really slow. What should I try?**
A: Check `NovaRetail-Staff`, move to an open work area, pause nonessential transfers, reconnect once, and try an assigned wired connection. Report the location and whether colleagues are affected.

**Q: How do visitors get online?**
A: Visitors select `NovaRetail-Guest` and accept the guest network-use terms in a browser. NovaRetail guest Wi-Fi requires no company account and provides internet only.
