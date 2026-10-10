# deepseek-v4-pro via https://api.deepseek.com, tools, 2026-10-10 12:03 UTC

**User:** https://victoryskating.com/doubleaxel Tell me about this program: price, coach, schedule, number of classes and level.

> tool: `search_offerings(query="double axel program")`
> tool: `get_offering_details(offering_id="double-axel-club")`

**Assistant:** Here's what I found for the program at that link — the **6-Month Double Axel Club**:

**Level:** Level 3. Prerequisite: you're already proficient in double jumps off-ice.

**Coach:** Coach Marta (international figure skating coach; trained at MKS Axel Toruń in Poland and with Team Mayer-Virtanen in Finland; degree in Physical Education).

**Schedule:** 2 live online classes per week — every Saturday and Sunday — each 45 minutes. (Times depend on your timezone; e.g., this weekend's Saturday session is at 10:00 AM EDT / 3:00 PM London / 4:00 PM Berlin.)

**Number of classes:** 48 live group classes over 6 months.

**Price:** $299 USD (list price $699, so 57% off) — about $6.23 per class. It bills **$299 every 6 months and renews automatically until cancelled**. It is **non-refundable**, and you can cancel at least 48 hours before the next payment date via the Subscriptions link in the confirmation email.

**What's included:**
- 2 live group classes every Saturday and Sunday
- Free 4-day 2Axel Workbook
- $5 discount on your next private class
- 2 free group-class passes for friends or relatives
- Structured 6-month progression into harder double jumps and triple jumps

**Required equipment:** sneakers, a jump rope, an off-ice spinner, stable internet, and some space to train.

**Enrollment:** Open continuously — you can join any time and start at the next scheduled session (access details arrive within 24 hours of payment).

Would you like me to check availability for a specific start date (and if so, what timezone are you in)?

---

**User:** I'm free on November 6. Can I join around that time?

> tool: `check_availability(offering_id="double-axel-club", date="2026-11-06")`

**Assistant:** Good news — yes, you can join. Enrollment is rolling, so you can sign up any time and start at the next scheduled session.

Since November 6 is a Friday, your first class would be the next weekend:
- **Sat 7 Nov 2026, 07:00–07:45 PST**
- **Sun 8 Nov 2026, 07:00–07:45 PST**
- Then every Saturday and Sunday after that.

Note: those times are shown in **America/Los_Angeles (PST)**. If you tell me your timezone, I can give you the exact local class times.

Would you like me to set you up with the checkout link to enroll?

---

**User:** What time would the classes be for me in Bangkok in November?

> tool: `check_availability(date="2026-11-06", offering_id="double-axel-club", timezone="Asia/Bangkok")`

**Assistant:** In Bangkok (UTC+07), the classes run at **22:00–22:45** in the evening:

- **Sat 7 Nov 2026, 22:00–22:45**
- **Sun 8 Nov 2026, 22:00–22:45**
- **Sat 14 Nov 2026, 22:00–22:45**
- **Sun 15 Nov 2026, 22:00–22:45**

…and every Saturday and Sunday after that.

Would you like me to create the checkout link so you can enroll?

---

**User:** Is it a one-time payment or a subscription? Does it renew, and can I get a refund?

**Assistant:** It's a **subscription**, not a one-time payment:

- **Billing:** $299 USD every 6 months, and it **renews automatically until you cancel**.
- **Refunds:** It is **non-refundable**.
- **Cancellation:** You can cancel at least **48 hours before the next payment date** via the Subscriptions link in the confirmation email.

So you pay $299 now, get 6 months (48 classes), and it will automatically charge $299 again every 6 months unless you cancel before that date.

Would you like me to create the checkout link to enroll?

---

**User:** My email is vladimir.mizin1@gmail.com. I want to join.

> tool: `create_checkout_link(offering_id="double-axel-club", email="vladimir.mizin1@gmail.com", timezone="Asia/Bangkok", date="2026-11-06")`

**Assistant:** Here's your enrollment link:

**https://buy.stripe.com/14AeVd6anbti69kcJ9dMM1M?client_reference_id=f6f13e8538ad48228e518f0f21e4d0bc&prefilled_email=vladimir.mizin1%40gmail.com**

Just to confirm the terms before you pay:
- **Price:** $299 USD (list price $699) for the 6-Month Package — 48 live classes over 6 months.
- **Billing:** $299 every 6 months, **renews automatically until cancelled**.
- **Cancellation:** Cancel at least 48 hours before the next payment date via the Subscriptions link in the confirmation email.
- **Refunds:** Non-refundable.

After payment, your access details arrive within 24 hours, and your first session will be **Sat 7 Nov 2026, 22:00–22:45 (Bangkok time)**.

Let me know if you have any other questions!

---
