# NovaRetail Password Policy and Reset

- Document ID: NR-IT-001
- Owner: Service Desk
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: All employees and contractors with NovaRetail accounts

## Purpose

Use this guide to reset a NovaRetail password, handle an account lockout, and respond to a password that might be compromised.

## Choose a password that meets NovaRetail rules

A NovaRetail password must contain at least 14 characters and must not match any of your last 12 passwords. A passphrase is encouraged because a longer combination of words is easier to remember.

- NovaRetail passwords have no scheduled expiry.
- Change a password immediately if it might be compromised.
- Choose a different password from the one you use for personal accounts.
- Company apps use single sign-on with your company email, password, and MFA.
- Never share a password with another person.

IT staff and the Service Desk never ask for your password or an MFA code through any channel, including in person. Report such a request to `security@novaretail.example` as suspected social engineering.

## Reset your NovaRetail password yourself

To reset your NovaRetail password, use `https://password.novaretail.example`; self-service password reset requires MFA.

1. Open the password portal directly rather than following an unexpected message.
2. Enter your company email and choose the password reset option.
3. Complete the MFA verification you started.
4. Choose a password of at least 14 characters that is not one of your last 12 passwords.
5. Finish the reset and sign in to the company app again.

The new password applies to company apps through single sign-on. Do not send the password, an MFA code, or a screenshot containing either to support. If MFA is unavailable, contact the Service Desk for identity verification.

## Handle a locked-out NovaRetail account

A NovaRetail account becomes locked out after 5 failed sign-in attempts and unlocks automatically after 15 minutes. Repeated attempts during the wait are not a useful troubleshooting step.

1. Stop entering passwords and wait the full 15 minutes after the lockout began.
2. Check that you are using your company email and the intended keyboard settings.
3. If you forgot the password, use `https://password.novaretail.example` with MFA.
4. After the lockout period, try signing in with the correct password.
5. If sign-in still fails, contact `+1-555-0142` and describe the error.

Tell the Service Desk when the lockout started and whether another app is repeatedly requesting credentials. Never include the password in a ticket.

## Respond to a possibly compromised NovaRetail password

A possibly compromised NovaRetail password must be changed immediately, even though NovaRetail passwords have no scheduled expiry. Treat a password entered into a suspicious page or shared with a caller as compromised.

1. Open `https://password.novaretail.example` directly and reset the password using MFA.
2. Reject any MFA prompt you did not start.
3. Report the suspected compromise to `security@novaretail.example`.
4. Call `+1-555-0142` immediately if you cannot reset the password or someone appears to be using the account.

Include the time, affected company app, and what happened, but not the password or MFA code. A confirmed security incident is P1 and receives phone support 24x7.

## Get help when NovaRetail password reset is unavailable

NovaRetail password reset assistance is available from the Service Desk when the password portal cannot be reached or you cannot complete MFA.

1. Call `+1-555-0142`, or use extension `4357` on a company phone.
2. Explain whether the problem is a locked account, a portal error, or an unavailable MFA method.
3. Arrange for your manager to confirm your identity on a Teams call before an assisted password or MFA reset.
4. Follow the Service Desk instructions without sharing your password or an MFA code.

For a new or lost phone, the verified MFA recovery process provides a Temporary Access Pass valid for 8 hours. Routine Service Desk hours are 07:00-21:00, 7 days a week, local time.

## Frequently asked questions

**Q: How long does my password need to be?**
A: A NovaRetail password needs at least 14 characters. A passphrase is encouraged, and the last 12 passwords cannot be reused.

**Q: Do I have to change my password every month?**
A: NovaRetail passwords have no scheduled expiry. Change a NovaRetail password immediately if it might be compromised.

**Q: I'm locked out. Should I keep trying?**
A: A NovaRetail account locks after 5 failed attempts and unlocks automatically after 15 minutes. Stop trying, wait, and reset a forgotten password through `https://password.novaretail.example` using MFA.

**Q: Can support reset my password without MFA?**
A: For an assisted NovaRetail password reset, the Service Desk first verifies identity through your manager on a Teams call. Support never needs your password or an MFA code.
