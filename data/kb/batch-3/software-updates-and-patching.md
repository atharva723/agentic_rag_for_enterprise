# NovaRetail Software Updates and Patching

- Document ID: NR-IT-015
- Owner: Service Desk
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Employees using company devices, including Windows 11 laptops

## Purpose

Use this guide to complete required NovaRetail updates, meet Windows 11 restart deadlines, and resolve update failures without bypassing device controls.

## Understand NovaRetail monthly Windows updates

NovaRetail Windows 11 updates install monthly on company laptops. Updates protect the approved company build and must not be disabled or replaced by an employee-installed operating system.

- Keep the laptop powered and connected to a reliable network during installation.
- Save active work before starting a restart.
- Follow company update prompts rather than an unexpected email download.
- Approved application software is installed and updated through Software Center.
- Full-disk encryption remains enabled during normal company updating.

The monthly schedule and restart deadlines in this guide apply to Windows 11. Employees with company Macs follow the device's company update instructions and contact the Service Desk if installation fails; no Mac-specific schedule is defined here.

## Meet the NovaRetail 3-day restart deadline

NovaRetail Windows update prompts allow 3 days to restart before an automatic restart outside 09:00-18:00. Use that period to choose a restart time after saving work.

1. Read the company update prompt and note the restart requirement.
2. Save documents in OneDrive or SharePoint and check synchronization.
3. Close active work and finish any transaction that must not be interrupted.
4. Restart through the device's normal restart controls.
5. Allow installation to finish and sign in again.

The deadline is 3 days, not 3 business days. Do not repeatedly defer the prompt or leave unsaved work overnight expecting the laptop to remain running. Report a restart failure to the Service Desk.

## Understand an automatic NovaRetail laptop restart

An automatic NovaRetail Windows 11 restart occurs after the 3-day restart allowance when required updates still need a restart. Automatic restarts are scheduled outside 09:00-18:00.

1. After sign-in, check whether the device reports that updates completed.
2. Reopen work apps and check saved files in OneDrive or SharePoint.
3. Report missing work or an installation error through `https://itportal.novaretail.example`.
4. Include the restart time, displayed message, and whether the laptop had already restarted for the update.

Do not disable updating to prevent another restart. A restart inside 09:00-18:00 or before the stated allowance needs investigation; report it rather than assuming it matches the automatic-restart policy. Local-disk-only files are not backed up.

## Restore VPN access after NovaRetail update noncompliance

NovaRetail laptops not restarted for 7 days may lose VPN access until they are updated. This is a compliance restriction, not permission to install another VPN or bypass company management.

1. Check the laptop's update and restart warnings.
2. Connect to a reliable internet connection and keep the charger connected.
3. Complete required company updates.
4. Save work and restart Windows 11.
5. Reopen NovaConnect VPN and sign in with company email, password, and MFA.

If access remains blocked after successful updating, report the warning and exact VPN error to the Service Desk. NovaConnect error `NC-420` separately means the VPN client is out of date and must be updated in Software Center.

## Report a NovaRetail update that keeps failing

A NovaRetail update that repeatedly fails must be reported with its error and attempted checks, rather than hidden by disabling updates.

1. Note the displayed error code, update name, and failure time.
2. Check that the laptop has internet access and the approved charger connected.
3. Save work, restart normally, and retry the company update once.
4. If failure repeats, submit a ticket at `https://itportal.novaretail.example`.
5. State whether you can sign in, restart successfully, and connect to NovaConnect VPN.

Do not download replacement update packages, change security settings, or reinstall the operating system. If the laptop cannot start, call `+1-555-0142`. The Service Desk assesses the work impact and any need for a loaner.

## Frequently asked questions

**Q: Why did my laptop restart by itself?**
A: NovaRetail Windows updates allow 3 days for a restart, then trigger an automatic restart outside 09:00-18:00. Report behavior that does not match those conditions.

**Q: How long can I wait before restarting?**
A: NovaRetail Windows 11 updates give you 3 days, not business days, to restart. Save work and restart before the automatic-restart deadline.

**Q: Why was VPN access blocked after an update warning?**
A: A NovaRetail laptop not restarted for 7 days may lose VPN access until updated. Complete required updates and restart before reconnecting.

**Q: An update keeps failing. What do I send IT?**
A: Send the NovaRetail update name, exact error, failure time, and checks attempted. Include whether the laptop can sign in and use VPN.
