# NovaRetail MFA Policy and Setup

- Document ID: NR-IT-002
- Owner: Security team
- Version: 1.0
- Last reviewed: 2026-10-15
- Audience: All employees and contractors with NovaRetail accounts

## Purpose

Use this guide to set up NovaRetail multifactor authentication, recover access after changing phones, and handle unexpected approval requests.

## Use an approved NovaRetail MFA method

NovaRetail MFA uses Microsoft Authenticator push approval with number matching as the standard method. Sign-in combines your company email, password, and MFA.

- Approve an Authenticator request only when you started the corresponding sign-in.
- Match the number displayed by your sign-in with the Authenticator request.
- Hardware security keys are available on request for admins and executives through `https://itportal.novaretail.example`.
- SMS codes and voice-call codes are not allowed.
- Personal phones can use Authenticator under app protection without full device management.

Neither IT staff nor the Service Desk will ask you to share an MFA code or password by phone, chat, email, or in person. Report anyone who does to `security@novaretail.example`.

## Set up Microsoft Authenticator for the first time

To set up NovaRetail MFA for the first time, use Microsoft Authenticator and the security-information registration process presented during company sign-in.

1. Get Microsoft Authenticator on your phone through the approved app installation process for that device.
2. Start company sign-in with your company email and the initial access instructions provided by the Service Desk.
3. Choose to register Authenticator as a work account.
4. Follow the registration instructions on your computer and phone; scan the registration code if offered.
5. Complete the test approval using number matching.
6. Confirm that another company sign-in prompts the registered phone.

If registration cannot start, contact the Service Desk. Never send support your registration code, password, or MFA code.

## Move NovaRetail MFA to a new phone

To move NovaRetail MFA to a new phone, contact the Service Desk rather than assuming the phone transfer also moved your work authentication registration.

1. Call `+1-555-0142` and explain that you are replacing the phone used for Authenticator.
2. Have your manager confirm your identity on a Teams call.
3. Receive a Temporary Access Pass valid for 8 hours.
4. Use the pass to access the company security-information registration process.
5. Register Microsoft Authenticator on the new phone and complete a number-matching test.
6. Remove the old phone's authentication registration after the new registration works.

Keep the Temporary Access Pass private and use it within its 8-hour validity.

## Recover NovaRetail MFA after losing a phone

NovaRetail MFA recovery after a lost phone requires Service Desk identity verification; SMS and voice-call codes are not substitutes.

1. Call `+1-555-0142` and state that your Authenticator phone is missing.
2. If the missing phone is a company device, report the loss within 1 hour of noticing through the 24x7 phone line.
3. Arrange your manager's identity confirmation on a Teams call.
4. Receive a Temporary Access Pass valid for 8 hours and register Authenticator on a replacement phone.
5. Ask the Service Desk to remove the lost phone's authentication registration.

IT remotely locks and wipes lost company devices. Report lost work access on a personal phone; app protection does not provide full-device management or a whole-phone wipe.

## Stop NovaRetail MFA prompts you did not start

Unexpected NovaRetail MFA prompts can indicate that someone is attempting to sign in as you. Do not approve a request to stop repeated notifications.

1. Reject the prompt; use a report option if Authenticator offers one.
2. Do not enter a number supplied by a caller or message.
3. Report the prompts, their times, and the affected account to `security@novaretail.example`.
4. Change your company password immediately at `https://password.novaretail.example` if it might be compromised.
5. Call `+1-555-0142` immediately if you approved an unexpected prompt or cannot secure the account.

A confirmed security incident is P1 with 24x7 phone support. Never provide your password or an MFA code as evidence.

## Frequently asked questions

**Q: Can IT ask me for my MFA code?**
A: NovaRetail IT and the Service Desk never ask for an MFA code or password through any channel. Report the request to `security@novaretail.example`.

**Q: I have a new phone. Will Authenticator just transfer?**
A: NovaRetail MFA registration must be checked and moved through the Service Desk recovery process. Your manager confirms identity on a Teams call, and the Service Desk issues an 8-hour Temporary Access Pass.

**Q: How do I sign in if I lost my phone?**
A: Call `+1-555-0142` for NovaRetail MFA recovery. After manager confirmation on a Teams call, the Service Desk issues a Temporary Access Pass valid for 8 hours.

**Q: I keep getting approval requests. Should I accept one?**
A: Reject NovaRetail MFA prompts you did not start and report them to the Security team. Change a possibly compromised password immediately; call the Service Desk if you already approved a prompt.
