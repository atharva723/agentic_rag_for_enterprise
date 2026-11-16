# NovaRetail Mobile Devices and Personal Phone Rules

- Document ID: NR-IT-014
- Owner: Security team
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Employees using company phones or approved work apps on personal phones

## Purpose

Use this guide to request a managed company phone, understand personal-phone work limits, and recover access after a phone is replaced or lost.

## Request a managed NovaRetail company phone

A NovaRetail company phone is provided for an approved work requirement and is managed through mobile device management, or MDM. Request a company phone through `https://itportal.novaretail.example`.

1. Explain the business need and include your manager and work location.
2. Obtain manager approval.
3. Allow the standard fulfillment target of 2 business days after approval.
4. Follow the Service Desk's collection or delivery instructions.
5. Complete the company management setup before using work apps.

Business days are Monday through Friday, excluding company holidays. MDM enforces company device settings and supports remote lock and wipe. Do not remove management controls or install unapproved software; use the company-approved installation process.

## Understand NovaRetail personal-phone app protection

NovaRetail personal phones, also called BYOD, are allowed only for Microsoft Authenticator, Outlook, and Teams under app protection. A personal phone is not enrolled in full device management.

- App protection controls company data within the approved work apps.
- App protection can remove company app data when access must be withdrawn.
- App protection does not manage personal photos, personal messages, or the whole phone.
- OneDrive, SharePoint, and other work apps are not approved for BYOD.
- NovaConnect VPN is not available on personal devices.
- Personal phones use `NovaRetail-Guest`, not `NovaRetail-Staff`, on company sites.

Company-managed phones use MDM instead. Do not assume that the personal-phone app-protection model also describes a company-owned phone.

## Set up approved NovaRetail apps on a personal phone

NovaRetail personal-phone setup uses Service Desk installation instructions and work-app protection before accessing company data. Do not enroll the personal device into company MDM.

1. Obtain the approved setup instructions through `https://itportal.novaretail.example` or the Service Desk.
2. Get Microsoft Authenticator, Outlook, and Teams through the instructed app installation process.
3. Register Authenticator for your company account and complete the number-matching test.
4. Sign in to Outlook and Teams with your company email, password, and MFA.
5. Accept the required work-app protection controls.
6. Confirm that work email and Teams function without installing other work apps.

If setup requests full device management, stop and contact the Service Desk. Never share a password or MFA code.

## Move NovaRetail mobile access to a new phone

NovaRetail mobile access on a new phone requires a fresh work-app setup and a checked Authenticator registration. A personal phone transfer does not prove that company MFA registration transferred correctly.

1. Contact `+1-555-0142` and explain the phone replacement.
2. Arrange for your manager to confirm identity on a Teams call.
3. Receive the Service Desk's Temporary Access Pass, valid for 8 hours.
4. Register Microsoft Authenticator on the replacement phone and test number matching.
5. Set up Outlook and Teams with the appropriate app protection or company MDM.
6. Remove the old authentication registration after the new phone works.

Keep the Temporary Access Pass private. Do not approve a prompt you did not start during the migration.

## Report a lost NovaRetail company or personal phone

A lost NovaRetail company phone must be reported to `+1-555-0142` within 1 hour of noticing through the 24x7 phone line. IT remotely locks and wipes the company device.

1. State whether the missing phone is company-owned or personal.
2. Explain whether it held company apps or Microsoft Authenticator.
3. For a personal phone with work apps, report promptly so work access and company app data can be protected.
4. Arrange manager confirmation on a Teams call for MFA recovery.
5. Use an 8-hour Temporary Access Pass to register a replacement phone.

Personal-phone app protection does not provide a whole-phone remote wipe. The Service Desk removes the lost authentication registration and coordinates work-access protection with the Security team.

## Frequently asked questions

**Q: Can I use my personal phone for work email?**
A: NovaRetail allows Outlook on a personal phone under app protection. Authenticator and Teams are the only other approved BYOD work apps.

**Q: Does IT manage everything on my personal phone?**
A: NovaRetail BYOD uses work-app protection, not full device management. It controls and can remove company app data, but does not manage personal photos, messages, or the whole phone.

**Q: How do I get a company phone?**
A: Request a NovaRetail company phone through the NovaIT Portal with a business reason and manager approval. Standard fulfillment targets 2 business days after approval, and the phone uses MDM.

**Q: Will IT wipe my lost personal phone?**
A: NovaRetail app protection can remove company app data but does not wipe the entire personal phone. Lost company phones are remotely locked and wiped.
