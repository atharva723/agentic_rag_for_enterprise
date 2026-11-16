# NovaRetail Service Desk Agent Runbook

- Document ID: NR-IT-025
- Owner: Service Desk
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: Service Desk agents handling company support tickets

## Purpose

Use this runbook for verified resets, ten common issues, escalation, and complete ticket closure.

## Verify NovaRetail identity before an assisted reset

NovaRetail assisted password or MFA resets require manager confirmation on a Teams call. Agents never ask for passwords or MFA codes through any channel.

1. Record the claimed company account and requested action without secrets.
2. Find the manager through company records, not caller-supplied contacts.
3. Arrange the manager's Teams confirmation of identity.
4. Record manager confirmation and verification time in the ticket.

Do not reset before confirmation. Escalate verification difficulties; personal trivia or unverified messages cannot replace the manager call.

## Issue a NovaRetail Temporary Access Pass

A NovaRetail Temporary Access Pass requires manager verification for a new or lost Authenticator phone. The pass is valid for 8 hours.

1. Record the phone-recovery reason.
2. Verify identity through the manager's Teams call.
3. Generate the pass through approved recovery controls.
4. Deliver it privately; never store its value in notes.
5. Guide Authenticator registration and number-matching testing.

Remove a lost phone's registration. Never request the pass back as evidence or substitute SMS or voice-call codes.

## Triage NovaRetail account and VPN sign-in issues

NovaRetail account and VPN triage records impact, scope, start time, error, and workaround for four common issues.

1. Cannot sign in: check company email; offer MFA-protected reset at `https://password.novaretail.example`.
2. Locked out: 5 failed attempts cause a 15-minute automatic lockout; stop retries.
3. MFA unavailable: identify phone loss or replacement; verify before recovery.
4. VPN failure on Windows 11: check internet and `vpn.novaretail.example`; `NC-101` means bad credentials, `NC-203` MFA timeout, `NC-310` internet or DNS failure, and `NC-420` outdated client requiring Software Center update.

Mac users follow the Mac guide on the NovaIT Portal; never collect secrets.

## Triage NovaRetail laptop and update problems

NovaRetail laptop triage uses external checks, not employee repairs or encryption changes, for three device issues.

1. Laptop won't turn on: check approved charger and outlet, bypass the dock, and note power indicators.
2. Slow laptop or frozen app: save work, close unused apps, restart, and record affected apps.
3. Update failure: capture the error, check power and internet, restart, and retry once.

Windows updates allow 3 days to restart. A laptop not restarted for 7 days may lose VPN access until updated. Investigate continuing failures.

## Triage NovaRetail printing and collaboration problems

NovaRetail shared-service triage records resource, device, error, and affected users for three common issues.

1. Printer missing: check company network, install `NovaRetail Printing` through Software Center, and confirm `NovaRetail Follow-Me`.
2. Teams audio or frozen app: check mute, devices, and permissions; reopen Teams and test fresh sign-in.
3. SharePoint access denied: check company account and permissions; missing access requires manager and resource-owner approval.

Do not widen sharing or delete guessed cache folders. Record checks and results.

## Escalate NovaRetail incidents by impact

NovaRetail escalation routes store problems to Store IT and security concerns to the Security team. P1 covers location down, POS down, many blocked users, or confirmed security incidents.

- P1: 15-minute first response and 4-hour target fix, 24x7.
- P2: 2-hour first response and 1-business-day target fix.
- P3: 1-business-day first response and 3-business-day target fix.
- P4: 2-business-day first response and 5-business-day target fix.

Business days are Monday-Friday, excluding company holidays; P2 response hours follow Service Desk hours, 07:00-21:00 daily, local time. An `ESCALATE` email or phone request quoting the ticket notifies the Service Desk Manager.

## Close a NovaRetail ticket with verified results

NovaRetail ticket closure requires a recorded resolution and confirmation that the intended task works, not merely a vanished error.

1. Record issue, impact, priority, and resource.
2. Summarize checks, results, established cause, and actions.
3. Note approvals, required verification, and escalation outcomes.
4. Record the employee's test, result, and confirmation time.
5. Explain remaining limitations or follow-up.

Exclude passwords, MFA codes, Temporary Access Pass values, and sensitive contents. Keep the ticket open until the employee confirms the result.

## Frequently asked questions

**Q: How does an agent verify identity?**
A: NovaRetail assisted resets require manager confirmation on a Teams call. Find the manager through company records and record verification without secrets.

**Q: When can I issue a Temporary Access Pass?**
A: For a new or lost Authenticator phone, after NovaRetail manager identity confirmation. The pass lasts 8 hours; do not store its value in notes.

**Q: What are the first VPN checks?**
A: On Windows 11, check internet, the NovaConnect gateway, and the exact error code. Check update compliance and resolve the indicated credentials, MFA, connection, or client problem.

**Q: What must closure notes contain?**
A: NovaRetail notes need impact, priority, checks and results, resolution, approvals, and the employee's successful test and confirmation time. Record limitations and follow-up, never secrets.
