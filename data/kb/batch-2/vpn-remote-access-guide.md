# NovaConnect VPN Remote Access for Windows 11

- Document ID: NR-IT-006
- Owner: Service Desk
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Employees using company Windows 11 laptops off site

## Purpose

Use this guide to connect and troubleshoot NovaConnect VPN on Windows 11. Mac users follow the Mac guide on `https://itportal.novaretail.example`; this document provides no Mac VPN steps.

## Decide when NovaConnect VPN is needed

NovaConnect VPN is required for internal systems when you are off site using a company laptop. Internal systems include the intranet, NovaERP, and company file shares.

- Microsoft 365, including Outlook, Teams, OneDrive, and SharePoint, does not need the VPN.
- NovaConnect uses split tunneling: only internal-system traffic passes through the VPN.
- NovaConnect VPN is not available on personal devices.
- HQ employees can work from home up to 2 days a week; store and DC employees work on site.

Check which system is failing before troubleshooting the VPN. A successful Teams connection does not prove that the VPN is connected or that NovaERP is reachable.

## Connect NovaConnect VPN from home

To connect NovaConnect VPN from home on Windows 11, first establish internet access on your company laptop.

1. Connect the laptop to your home network and confirm an internet page opens.
2. Open the pre-installed NovaConnect VPN client.
3. Enter `vpn.novaretail.example` in `Gateway` if the gateway is not already configured.
4. Select `Connect` and enter your company email and password.
5. Complete the Microsoft Authenticator approval using number matching for the sign-in you started.
6. Wait for `Connected`, then open the required internal system.

If NovaConnect is missing, install it through Software Center. Never share your password or an MFA code with IT staff or the Service Desk.

## Resolve NovaConnect VPN error codes

NovaConnect VPN error codes identify the first check to perform; include the exact code in a support ticket rather than describing every failure as a bad password.

- `NC-101`: bad credentials. Check your company email and password; use `https://password.novaretail.example` with MFA if a reset is needed.
- `NC-203`: MFA timed out. Start a fresh connection and complete the Authenticator number-matching approval.
- `NC-310`: no internet or DNS failure. Check ordinary internet access before retrying.
- `NC-420`: client out of date. Update NovaConnect VPN in Software Center.

After 5 failed password attempts, the account locks for 15 minutes and unlocks automatically. Stop repeated attempts. Report continuing failures at `https://itportal.novaretail.example` with the code and time.

## Recover a disconnected NovaConnect VPN session

A NovaConnect VPN session ends after 12 hours, so a disconnect at that limit is expected. Save work and establish a fresh connection with your company email, password, and MFA approval.

1. Check whether the laptop still has internet access.
2. Reopen NovaConnect and select `Connect`.
3. Complete your own MFA request and check for `Connected`.
4. If access is blocked, check for update or restart warnings.
5. Install required updates and restart the laptop before testing again.

A laptop not restarted for 7 days may lose VPN access until updated. For repeated earlier disconnects, report their times, any error code, and whether the home network also dropped.

## Install or reinstall NovaConnect VPN safely

NovaConnect VPN installation and reinstallation on Windows 11 must use Software Center, not a download sent by a caller or an internet search result.

1. Save work and close NovaConnect VPN.
2. Open Software Center and locate NovaConnect VPN.
3. If the client is missing, select `Install`.
4. To reinstall an installed client, select `Uninstall`, then `Install`.
5. Restart Windows 11 if requested and connect to `vpn.novaretail.example`.

For `NC-420`, use the available update in Software Center before considering reinstallation. If installation actions are unavailable or fail, submit the error to the Service Desk. Company laptops have no local admin rights; do not attempt to bypass that restriction.

## Frequently asked questions

**Q: How do I get on the VPN from home?**
A: On a company Windows 11 laptop, open NovaConnect, connect to `vpn.novaretail.example`, and sign in with company email, password, and MFA. Confirm `Connected` before opening internal systems.

**Q: Do Teams and Outlook need the VPN?**
A: Teams and Outlook do not require NovaConnect VPN. Neither do OneDrive or SharePoint; off-site internal systems such as NovaERP do require it.

**Q: What does NC-203 mean?**
A: NovaConnect error `NC-203` means MFA timed out. Start the VPN connection again and complete the Authenticator number-matching request you initiated.

**Q: Why does the VPN drop after several hours?**
A: NovaConnect sessions end after 12 hours. Reconnect with MFA; report earlier repeated disconnects with their times and error codes.
