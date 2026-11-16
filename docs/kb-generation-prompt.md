# Knowledge-base generation prompts

Two prompts for ChatGPT. Together they create the knowledge base (25 IT-support documents) and a set of test questions for the fictional company NovaRetail. The new documents replace the old sample files.

## How to use

1. Open a new ChatGPT chat and paste **Prompt 1**. You may edit names and numbers in COMPANY FACTS first, but keep them consistent.
2. ChatGPT sends 5 documents per batch. Type `NEXT` after each batch (5 batches in total).
3. Save the files into `data/kb/` with the exact file names ChatGPT gives them. The `batch-1` to `batch-5` folders can stay as they are: ingest reads subfolders too.
4. In the same chat, paste **Prompt 2**. Save the JSON it returns as `tests/eval_questions.json`.
5. Load the documents into Pinecone with `python -m app.rag.ingest` (setup steps are in `app/rag/README.md`).

## Why the documents are written this way

- The app cuts each document into chunks of about 900 characters. Short sections that make sense on their own give clean chunks.
- Each document ends with an FAQ in the words employees really use. A question matches a question well in vector search.
- The gaps are on purpose: no vendor outage news, no macOS VPN steps, no costs. They let us test the web fallback and the "not enough evidence" answer.
- The BRD demo questions are covered, for example VPN from home (`vpn-remote-access-guide.md`) and the MFA code rule (`mfa-policy-and-setup.md`).

## Prompt 1 - the documents

````text
ROLE
You are a senior IT service-management technical writer. You are creating a synthetic IT support knowledge base for a fictional company. The documents will be loaded into a RAG chatbot: each file is cut into chunks of about 900 characters, the chunks are found by vector search, and an LLM answers ONLY from the chunks it finds. Write for retrieval quality and factual precision, not for style.

COMPANY FACTS
Ground truth. Never contradict these and never invent different values for them. Use only the facts that matter for each document.
- Company: NovaRetail Inc., a retailer with about 3,000 employees: a head office (HQ), 2 distribution centres (DCs) and about 120 stores. HQ staff may work from home up to 2 days a week. Store and DC staff work on site.
- IT teams: Service Desk (first line), Store IT (store and POS support), Security team (incidents).
- Contacts: NovaIT Portal (tickets, requests, IT status) https://itportal.novaretail.example | Password portal https://password.novaretail.example | IT status page https://status.novaretail.example (planned maintenance and outages of NovaRetail's own systems only) | Service Desk phone +1-555-0142 (ext. 4357 on company phones) | servicedesk@novaretail.example | security@novaretail.example | Teams channel "IT Help" for quick questions.
- Service Desk hours: 07:00-21:00, 7 days a week, local time. P1 incidents: 24x7 on the phone line.
- Sign-in: company email + password + MFA, with single sign-on for all company apps.
- Passwords: at least 14 characters, passphrases encouraged. No scheduled expiry, but a password must be changed immediately if it may be compromised. The last 12 passwords cannot be reused. 5 failed attempts lock the account for 15 minutes (it unlocks by itself). Self-service reset is at the password portal and needs MFA.
- MFA: Microsoft Authenticator (push approval with number matching) is the standard. Hardware security keys on request for admins and executives. SMS and voice-call codes are NOT allowed. New or lost phone: the Service Desk verifies identity (the manager confirms on a Teams call) and issues a Temporary Access Pass valid for 8 hours.
- HARD RULE: IT staff and the Service Desk will NEVER ask for your password or an MFA code, by phone, chat, email or in person. Anyone who does is treated as a suspected social-engineering attempt and reported to the Security team.
- VPN: NovaConnect VPN client, pre-installed on company laptops (Software Center if missing). Gateway: vpn.novaretail.example. Sign in with company email, password and MFA approval. Split tunnel: only traffic to internal systems (intranet, NovaERP, file shares) uses the VPN. The VPN is required for internal systems when off site. It is NOT needed for Microsoft 365 (Outlook, Teams, OneDrive, SharePoint). Sessions end after 12 hours. Not available on personal devices. Error codes: NC-101 bad credentials, NC-203 MFA timed out, NC-310 no internet or DNS failure, NC-420 client out of date (update in Software Center).
- Devices: the standard laptop runs Windows 11 (Macs for the design and marketing teams). Full-disk encryption is always on. No local admin rights. Refresh every 4 years. Loaner laptops: same day at the HQ IT counter, next business day by courier to stores and DCs.
- Software: install only from Software Center. Not in the catalog: request it on the NovaIT Portal; it needs manager plus Security approval; target 2 business days.
- Printing: badge-based follow-me printing at any company printer.
- Mobile: company phones are managed (MDM). Personal phones (BYOD) are allowed only for Authenticator, Outlook and Teams under app protection, with no full device management.
- USB storage is blocked by default. Exceptions need a ticket and manager approval.
- Updates: Windows updates install monthly. Users have 3 days to restart before an automatic restart outside 09:00-18:00. A laptop not restarted for 7 days may lose VPN access until it is updated.
- Stores: Wi-Fi networks NovaRetail-Staff (company devices) and NovaRetail-Guest (customers, internet only). POS terminals run NovaPOS. In offline mode they accept cash and stored-value cards for up to 4 hours and decline card payments. A store with the POS down is P1: call the Service Desk and press 1.
- Priorities, as first response / target fix. P1 (a store, DC or HQ is down, POS is down, many users are blocked, or a confirmed security incident): 15 minutes / 4 hours, 24x7. P2 (a team is blocked or a key system is degraded): 2 hours / 1 business day. P3 (one person is blocked and there is no workaround): 1 business day / 3 business days. P4 (a how-to question or request, and a workaround exists): 2 business days / 5 business days. Escalation: reply "ESCALATE" to the ticket email, or call and quote the ticket number. The Service Desk Manager is notified.
- Lost or stolen device: report it to the 24x7 phone line within 1 hour of noticing. IT locks and wipes it remotely.
- Data classes: Public, Internal, Confidential, Restricted.
- Microsoft 365: Outlook, Teams, OneDrive, SharePoint. Files saved only on a laptop's local disk are not backed up. Work files belong in OneDrive or SharePoint.
- Real products you may name: Windows 11, macOS, Microsoft 365, Outlook, Teams, OneDrive, SharePoint, Microsoft Authenticator. Keep steps for them generic and do not invent exact menu paths. Internal tools (NovaConnect VPN, NovaIT Portal, NovaPOS, Software Center, NovaERP) may have invented but consistent screen labels.

DOCUMENTS
Write these 25 files, in 5 batches of 5. "Must answer" lists real employee questions that the file has to answer clearly and completely. Do not copy that wording; just make sure the answers are there.

BATCH 1 - Accounts and access
01 password-policy-and-reset.md - password rules, self-service reset, lockout, a compromised password. Must answer: How do I reset my password? My account is locked, what now? How long must my password be? Does my password expire?
02 mfa-policy-and-setup.md - approved methods, first-time setup, new or lost phone, MFA prompts you did not start. Must answer: Can IT support ask me to share my MFA code? I got a new phone, how do I move MFA? I lost my phone, how do I sign in? I keep getting MFA prompts I did not start, what do I do?
03 account-access-and-permissions.md - requesting access to apps, shared mailboxes and SharePoint sites; approvals; "access denied" errors; contractors. Must answer: How do I request access to a system? Who approves it and how long does it take? I get "access denied" on a SharePoint site. Can a contractor get an account?
04 new-hire-and-leaver-it-guide.md - IT on day one for new hires, equipment requests by managers, what happens when someone leaves. Must answer: What IT equipment do I get on day one? How far ahead must a manager request equipment? When is a leaver's access removed? What happens to a leaver's mailbox and files?
05 contacting-it-support-and-ticket-guide.md - channels, hours, creating and tracking a ticket, what to include, remote-support sessions. Must answer: How do I contact IT? What are the Service Desk hours? How do I raise a ticket and what should I put in it? Will a technician ever ask for my password?

BATCH 2 - Network, remote work and stores
06 vpn-remote-access-guide.md - connecting from home, when the VPN is and is not needed, disconnects, error codes, reinstalling the client. Windows 11 only (see GAPS). Must answer: How do I connect to the company VPN from home? Do I need the VPN for Teams or Outlook? What does error NC-203 mean? Why does my VPN disconnect after a while?
07 wifi-and-office-network.md - staff and guest Wi-Fi at HQ, DCs and stores, connecting, forgetting a network, wired ports, slow Wi-Fi. Must answer: Which Wi-Fi should I use? Can I put my personal phone on the staff Wi-Fi? The Wi-Fi is slow in the office, what can I try? How do visitors get internet?
08 working-from-home-and-travel-it-rules.md - home network basics, public Wi-Fi, travelling with a laptop, travel abroad rules (invent a clear rule, for example notify IT 5 business days before travel and use a loaner laptop for restricted countries). Must answer: Can I use my company laptop abroad? Do I need to tell IT before I travel? Is hotel or cafe Wi-Fi okay? What do I do if my home internet is down?
09 store-it-pos-and-store-network.md - POS problems, offline mode, card readers, receipt printers, store network down, who to call. Must answer: The POS is down in my store, what do I do? How long can the POS work offline? The card reader is not working. The receipt printer is offline or jammed.
10 ticket-priorities-slas-and-escalation.md - P1 to P4 definitions, response and fix targets, how to escalate. Must answer: What does P1 mean? How fast will IT respond to my ticket? My ticket has had no answer, how do I escalate? Who decides the priority?

BATCH 3 - Devices
11 laptop-troubleshooting.md - will not start, slow, overheating and fan noise, battery drain, blue screen, no sound, frozen apps. Must answer: My laptop will not turn on. My laptop is very slow. My battery drains fast. What do I do about a blue screen?
12 laptop-setup-refresh-and-loaners.md - standard build, first-time setup, the 4-year refresh, replacing a faulty or damaged laptop, loaners. Must answer: When do I get a new laptop? My laptop is damaged, how do I get a replacement or loaner? How long does a loaner take to reach a store? Can I install my own operating system?
13 printers-scanners-and-peripherals.md - follow-me printing, adding a printer, scanning to email, monitors, headsets, keyboards, docking stations. Must answer: How do I print with my badge? I cannot see any printer. How do I scan to email? Where do I get a headset or a monitor?
14 mobile-devices-and-byod.md - company phones, MDM, BYOD rules, setting up Outlook, Teams and Authenticator on a personal phone, a lost phone. Must answer: Can I use my personal phone for work email? What does the company manage on my personal phone? How do I get a company phone?
15 software-updates-and-patching.md - monthly updates, restart deadlines, automatic restarts, compliance and VPN access, failing updates. Must answer: Why did my laptop restart by itself? How long do I have to restart after an update? Why was my VPN blocked after an update warning? An update keeps failing, what now?

BATCH 4 - Software and collaboration
16 software-installation-and-approved-catalog.md - Software Center, catalog categories, requesting new software, licences, prohibited software. Must answer: How do I install software? The app I need is not in Software Center. How long does a software request take? Which software is not allowed?
17 microsoft-365-email-and-calendar.md - Outlook basics, mailbox size, attachment limit, shared mailboxes, calendar sharing, out-of-office replies, spam. Must answer: What is the maximum attachment size? How do I set an out-of-office reply? How do I add a shared mailbox? My mailbox is full.
18 microsoft-teams-usage-and-troubleshooting.md - meetings, chat, audio and video problems, notifications, clearing the cache, signing out and in, odd behaviour after an app update. NO outage or service-status content. Must answer: My microphone or camera does not work in Teams. Teams is slow or frozen. I am not getting notifications. Teams behaves strangely after an update.
19 file-storage-sharing-and-backup.md - OneDrive and SharePoint, sharing links, large files, recovering deleted files, laptop backup. Must answer: Where should I save work files? How do I share a file securely? How do I recover a deleted file? Is my laptop's local disk backed up?
20 acceptable-use-policy.md - acceptable use of company devices and accounts, limited personal use, prohibited actions, monitoring, consequences. Must answer: Can I use my work laptop for personal things? Can I install a personal VPN or a streaming app? Is my activity monitored? Can a family member use my laptop?

BATCH 5 - Security and operations
21 phishing-and-social-engineering.md - spotting phishing emails, texts and calls, fake IT staff, how to report, what to do after clicking. Must answer: How do I report a suspicious email? I clicked a link in a phishing email, what now? Someone phoned saying they were IT and asked for my password. How can I check that a caller really is from IT?
22 lost-or-stolen-device-and-security-incidents.md - report within 1 hour, what IT does, police report for theft, reporting a suspected data leak or breach. Must answer: I lost my laptop, what should I do? How fast must I report it? Will IT wipe my device? Who do I tell about a suspected data leak?
23 data-classification-and-removable-media.md - the four data classes with examples, handling rules, USB policy, sharing data outside the company. Must answer: What are the data classes? Can I email Confidential data outside the company? Can I use a USB drive? How do I ask for a USB exception?
24 planned-maintenance-and-outage-communication.md - how NovaRetail IT announces planned maintenance and outages of NovaRetail's OWN systems, where to look, what to do during an outage. NO mention of Microsoft or other vendor outages. Must answer: Where can I see whether a NovaRetail IT system is down? How are planned maintenance windows announced? Who declares an outage?
25 service-desk-agent-runbook.md - for Service Desk agents: triage steps, identity verification before a password or MFA reset, standard first steps for the top 10 issues, escalation, closing tickets. Agents never ask for a password or MFA code. Must answer: How does an agent verify someone's identity? When may an agent issue a Temporary Access Pass? What are the standard first steps for "cannot connect to VPN"? What must the notes contain when a ticket is closed?

GAPS (deliberate - do not cover these anywhere)
- macOS VPN steps. The VPN guide covers Windows 11 only and says Mac users follow the Mac guide on the NovaIT Portal (no steps given).
- Linux or any operating system other than Windows 11 and macOS.
- Outages, incidents or service status of Microsoft or any other vendor, and anything "current", "latest" or "recent": news, release notes, version numbers.
- Costs, prices, budgets and salaries.
- Credentials, inventories or equipment details for any specific store or person.
- HR, finance and legal topics.

FILE TEMPLATE
# <Title>

- Document ID: NR-IT-<the 3-digit number from the list, for example 006>
- Owner: <team name>
- Version: <for example 2.1>
- Last reviewed: <a date between 2026-03-01 and 2026-10-31>
- Audience: <who this applies to>

## Purpose
<1-2 sentences.>

## <A task or a question as the heading>
<70-140 words>

(5 to 7 such sections in total)

## Frequently asked questions

**Q: <a question as an employee would type it>**
A: <1-3 sentences that name the subject>

(3 to 5 pairs, each under 60 words)

WRITING RULES
1. One topic per document, one task or question per section. 500-800 words per document.
2. Each ## section is 70-140 words (Purpose and the FAQ are the only exceptions), so it fits in one chunk.
3. Every section must make sense on its own. Name the subject in the heading and in the first sentence ("To reset your NovaRetail password...", not "To do this..."). Never write "above", "below", "as mentioned" or "see section".
4. Use numbered steps for procedures (8 steps at most) and bullets for rules and lists. No tables, images, HTML, emojis or diagrams. Put commands, URLs, error codes and field names in inline code.
5. Be concrete: exact numbers, time limits, names, URLs from COMPANY FACTS, error codes, who approves and how long it takes. Avoid vague words such as "usually" or "may" unless the rule really is conditional.
6. Where natural, add conditions: HQ staff vs store or DC staff, managers vs employees, company device vs personal device.
7. Use the words employees really use ("locked out", "won't turn on", "Teams", "VPN") next to the formal terms.
8. No table of contents, "Related documents", "See also" or change-log section. Do not copy paragraphs from one document into another.
9. Never say that the company or the documents are fictional or synthetic. No placeholders such as [Company], TBD or lorem ipsum.
10. Use only .example domains, 555-01xx phone numbers and the teams named in COMPANY FACTS. No real people, no real companies (except the allowed products), no secrets or passwords.
11. Neutral, instructional tone. US English. No marketing language, no apologies, no "Welcome to".
12. Respect GAPS.

OUTPUT
- Start with BATCH 1 now. Then stop and wait for me to type NEXT.
- For each file, print a line "FILE: <file-name>.md", then the complete file inside a fenced block that uses ~~~markdown (tildes), so inner backticks do not break it.
- After each batch, print "FACTS ADDED:" with up to 10 bullets: any NEW concrete facts you invented (names, numbers, error codes, URLs) that are not in COMPANY FACTS. Later documents must reuse them exactly.
- If you run out of space, finish the current file, stop, and say which file to resume with. I will type NEXT.
- Before sending each batch, silently check every file against the rules above, COMPANY FACTS and its "Must answer" list. Fix problems first.
- If you can create downloadable files, you may make one ZIP per batch instead of printing the files. The content rules stay the same.
````

## Prompt 2 - the test questions

Paste this in the same chat after the 5th batch.

````text
Now create the test questions for the 25 documents you wrote. Output ONE valid JSON array and nothing else: no comments, no trailing commas, no text around it. It will be saved as tests/eval_questions.json.

Create exactly 33 items:
- 18 with category "kb": answerable from ONE document. Mix the styles: formal, casual, very short, vague, typo-ridden, and a long story with the question at the end. Spread them over at least 15 different documents.
- 4 with category "kb_multi": need facts from TWO documents.
- 4 with category "web": need current or public outside information that the documents deliberately do not have (for example current outages, latest versions, recent news).
- 3 with category "direct": greetings, thanks or small talk.
- 4 with category "no_answer": ask for company-internal facts that are neither in the documents nor on the public web (live data, credentials, personal data, equipment inventories).

Include these five questions word for word, and write the rest yourself without reusing the wording of the "Must answer" lists:
- "How do I connect to the company VPN from home?" (kb)
- "Can IT support ask me to share my MFA code?" (kb)
- "What is the latest Microsoft Teams outage guidance?" (web)
- "My work communication app is acting strange after the new update. What should I do?" (kb, vague)
- "Hello!" (direct)

Each item has exactly these fields:
{
  "id": "Q01",
  "category": "kb",
  "question": "...",
  "expected_path": "private_kb",
  "expected_files": ["vpn-remote-access-guide.md"],
  "must_mention": ["vpn.novaretail.example"],
  "notes": "short reason or demo name"
}

- id runs Q01 to Q33.
- expected_path is one of: "private_kb" (for kb and kb_multi), "web_search" (for web), "direct" (for direct), "fallback" (for no_answer).
- expected_files: the exact file names the answer comes from. Use [] for web, direct and no_answer.
- must_mention: 1 to 3 short strings copied exactly from the documents (numbers, names, URLs, error codes) that every correct answer must contain. Use [] for web, direct and no_answer.
- Only ask what the documents really answer. Do not write a kb question whose answer you cannot point to in a file.
````
