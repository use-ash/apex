# Getting Started with Apex

Welcome! This guide will walk you through setting up Apex from scratch. No technical experience required. Every step is explained in plain language, and you can always come back to this page if you get stuck.

**What you will have at the end:** A private AI chat running on your own computer, accessible from your browser and (optionally) your phone.

**Time needed:** About 10 minutes.

> **Stuck?** Open an issue at [github.com/use-ash/apex/issues](https://github.com/use-ash/apex/issues) — describe what happened, include a screenshot if you can, and someone will help.

---

## What is Apex?

Apex is an AI chat platform that runs entirely on your computer. Think of it like ChatGPT or Claude, but instead of your conversations going to someone else's servers, everything stays on your machine.

You can connect multiple AI models -- Claude, Codex (from OpenAI), Grok, and free local models -- and talk to all of them through one interface. Apex remembers your conversations across sessions, learns about your projects over time, and can read and write files on your computer (with your permission).

One computer. One app. Your data stays yours.

---

## What You Need Before Starting

- **A Mac, Linux, or Windows computer.**
- **Python 3.10 or newer.** Python is the programming language Apex is built with. You will not need to write any code or learn Python. It runs behind the scenes, like an engine in a car — you just need it installed. The installer checks for it automatically and tells you if it is missing. Apex runs inside a virtual environment, so it will not interfere with anything else on your system.
- **About 10 minutes of time.**

### Optional (but recommended)

These are not required. You can set up Apex with none of them and still use free local AI models. But if you have any of these, Apex can use them:

- **A Claude subscription** (Pro, Max, or Code plan at [claude.ai](https://claude.ai)) -- lets you use Claude, one of the most capable AI models available.
- **A ChatGPT subscription** (Plus or Pro plan at [chat.openai.com](https://chat.openai.com)) -- lets you use OpenAI's Codex models.
- **An xAI API key** (a secret code that lets Apex connect to the service) from [console.x.ai](https://console.x.ai) -- lets you use Grok, which can search the web and X/Twitter in real time. This is the only model that requires a separate API key.

> **No paid subscriptions?** No problem. Apex can run free local AI models on your computer with no account, no API key, and no internet connection. The setup wizard will offer to install one for you.

---

## Step 1: Download and Install Apex

Open the **Terminal** app. On Mac, you can find it by pressing `Cmd + Space`, typing "Terminal", and pressing Enter.

> **What is a terminal?** It is a text-based way to give commands to your computer. Instead of clicking buttons, you type instructions. It looks like a window with text and a blinking cursor. Everything in this guide that appears in a gray code box is something you type into the terminal.

Type the following three lines, pressing Enter after each:

```bash
git clone https://github.com/use-ash/apex.git ~/.apex
cd ~/.apex
bash install.sh
```

That's it. The installer handles everything:

1. **Finds Python** on your system (3.10 or newer required)
2. **Creates a virtual environment** so Apex's dependencies don't interfere with anything else on your computer
3. **Installs all dependencies** automatically
4. **Launches the setup wizard** which walks you through the rest

> **"git: command not found"?** Install git first:
>
> - **Mac:** Open Terminal and type `xcode-select --install`, then press Enter. Follow the prompts.
> - **Linux:** `sudo apt install git` (Ubuntu/Debian) or `sudo dnf install git` (Fedora)
>
> Then run the three commands above again.

> **"No suitable Python found"?** The installer needs Python 3.10+. On Mac, the easiest way to install it:
>
> - Go to [python.org/downloads](https://www.python.org/downloads/)
> - Download the latest version
> - Open the downloaded file and follow the installer
> - **Close and reopen Terminal**, then run `bash install.sh` again

---

## Step 2: The Setup Wizard

After `install.sh` finishes installing dependencies, it automatically launches the setup wizard. The wizard is an interactive program that configures everything for you. It asks questions, you answer them, and it does the rest.

> **Want to re-run the wizard later?** You can always run it again:
> ```bash
> cd ~/.apex
> .venv/bin/python3 setup.py
> ```

The wizard will ask you to choose between **Quick** and **Full** setup. We recommend **Full** for your first time -- it takes a few extra minutes but configures everything properly.

Type **F** and press Enter.

---

### Phase 1: Bootstrap (~2 minutes)

The bootstrap phase gets the basic infrastructure ready. Here is what happens at each step and what you need to do.

#### Step 1 of 7: Check Python packages

The wizard verifies that all required packages are installed in the virtual environment. Since `install.sh` already handled this, you should see green checkmarks. If anything is missing, the wizard installs it automatically.

> **What are packages?** They are pre-built building blocks that Apex uses. Think of them like ingredients in a recipe -- Apex needs them to work, but you do not need to know what they do.

#### Step 2 of 7: Create data folders

The wizard creates folders where Apex will store its data (conversations, settings, etc.). This happens automatically. Nothing to do here.

#### Step 3 of 7: Detect your network

The wizard finds your computer's network addresses (IP addresses). It shows something like:

```
Detected network interfaces:
  Wi-Fi:     192.168.1.42
  Loopback:  127.0.0.1
```

**Just press Enter** to accept the defaults. This is used so other devices (like your phone) can connect to Apex later.

> **What is an IP address?** It is your computer's address on the network, like a phone number. Other devices use it to find your computer. `127.0.0.1` is a special address that means "this computer" -- it always works for local access.

#### Step 4 of 7: Generate security certificates

> **What are certificates?** When you visit a website, certificates prove the site is who it claims to be. Apex creates its own certificates so your browser and the server can verify each other's identity. This is much more secure than passwords.

This step creates the files that keep your connection secure. The wizard handles everything — you just type "yes" and remember a password.

The wizard will show an explanation and ask you to confirm:

```
This will generate a local Certificate Authority and TLS certificates.
Type "yes" to continue:
```

Type **yes** and press Enter.

The wizard generates several files. The one you will need later is called `client.p12` -- it is like a digital ID card that your browser shows to prove it is allowed to connect.

You will see a password displayed on screen. **Write this password down** or remember it. You'll need this password in Step 3 when installing the certificate in your browser.

```
Certificate password: apex
```

#### Step 5 of 7: Choose your workspace

The wizard asks where the AI is allowed to read and write files:

```
Workspace directory [/Users/you/apex]:
```

**Press Enter** to accept the default (the Apex folder itself). If you want the AI to have access to a different folder (like your projects folder), type the path instead.

> **Tip:** You can always change this later from the Apex dashboard.

#### Step 6 of 7: Choose permission mode

This controls how much freedom the AI has to make changes on your computer:

```
Permission mode:
  [1] acceptEdits — AI can read and write files (recommended)
  [2] plan — AI suggests changes, you approve each one
  [3] full — AI can run any command (advanced users only)
```

Type **1** and press Enter. This is the recommended setting. The AI can read your files and make edits, but it asks before doing anything risky. (You can change this later from the dashboard.)

#### Step 7 of 7: Network access

The wizard asks who should be able to connect to your server:

```
Who should be able to connect to this server?
  [1] This computer only (localhost) — most secure, recommended for testing
  [2] Any device on my network (Wi-Fi, VPN) — required for phone/tablet access
```

- **Choose 1** if you only want to use Apex from this computer's browser. This is the safest option.
- **Choose 2** if you want to connect from your phone, tablet, or another computer on the same Wi-Fi network.

> **If you choose network access:** Apex uses client certificates (mTLS) to block unauthorized connections — only devices with your certificate can get in. But you should still only run Apex on a trusted network like your home Wi-Fi or a VPN. **Never expose Apex directly to the public internet.** If someone on your network doesn't have your client certificate, they cannot connect.

You can change this later by editing `APEX_HOST` in your launch script or config.

---

### Phase 2: Model Connections (~1 minute)

Now the wizard checks which AI models you can use and helps you connect them.

#### Claude (Anthropic)

The wizard checks if the Claude Code tool is installed on your computer.

- **If it is installed:** You will see a green checkmark. Claude uses your existing subscription automatically -- no API key needed.
- **If it is not installed:** The wizard offers to install it for you. Type **Y** to install. After installation, you need to sign in once: open a new Terminal window (Cmd+N), type `claude`, and press Enter. Follow the on-screen instructions to sign in with your Claude account. Then come back to this Terminal window.

> **How does this work without an API key?** Claude Code connects directly through your Claude subscription (the same one you use at claude.ai). Apex talks to Claude the same way the official Claude Code app does.

#### Codex (OpenAI)

Same process as Claude. The wizard checks for the Codex tool and offers to install it if missing. Uses your existing ChatGPT subscription.

#### Grok (xAI)

Grok is different from the others -- it needs an API key (a long string of characters that acts like a password for the service).

```
xAI API key (starts with xai-):
```

If you have an xAI account, paste your API key here and press Enter. If you do not have one, **just press Enter to skip**. You can always add it later.

> **Where do I get an xAI API key?** Go to [console.x.ai](https://console.x.ai), create an account, and generate an API key. It is pay-per-use (you pay for what you use, usually a few cents per conversation).

#### Local Models (Ollama)

This is the free option. Local models run entirely on your computer -- no internet, no account, no cost.

The wizard checks your hardware and asks if you want to install Ollama (the tool that runs local models):

```
Install Ollama for local AI models? [Y/n]
```

Type **Y** if you want free local models. The wizard will install Ollama and download a model for you. Depending on your internet speed and computer, this may take a few minutes.

> **How much computer power does this use?** Local models use your computer's processor and memory while they are actively responding. Modern Macs (especially those with Apple Silicon — M1, M2, M3, M4) handle this well, and the model only uses resources when you are chatting. The wizard checks your hardware before recommending a model.

#### Google API (for search features)

The wizard asks for a Google API key (a secret code that lets Apex connect to the service), which powers the semantic search feature (the AI's ability to search its own memory).

```
Google API key (starts with AIza):
```

**Skip this for now** — you can add it later from the dashboard. The AI works fine without it, it just won't be as good at recalling details from past conversations. If you do have a key, paste it and press Enter.

---

### Phase 3: Knowledge Ingestion (~2 minutes)

This phase teaches the AI about your workspace so it can be helpful from the first conversation.

#### Workspace scan

The wizard scans the folder you chose as your workspace. This is **read-only** -- it looks at file names, project structures, and documentation. It never uploads anything to the internet.

```
Scanning workspace...
Found: 3 projects, 47 markdown files, 12 config files
```

#### Review what it found

You will see a summary of what the wizard discovered. Review it to make sure it looks right.

#### Personality questions

The wizard asks three questions to configure how the AI communicates:

**1. Communication style:**
```
How should the agent communicate?
  [1] Direct — lead with the answer, concise
  [2] Thorough — detailed, cover edge cases, explain reasoning
  [3] Conversational — think out loud, invite input
```

Pick whatever feels right. Option 2 (Thorough) is a good default.

**2. Experience level:**
```
What's your experience level?
  [1] Peer — experienced developer, skip the basics
  [2] Mentor — explain concepts when relevant
  [3] Beginner — explain everything, suggest resources
```

Be honest here. If you are new to coding, pick option 3. There is no wrong answer.

**3. Personality:**
```
What personality fits best?
  [1] Professional — focused, efficient, minimal small talk
  [2] Collaborative — engaged partner, pushes back when needed
  [3] Friendly — warm, encouraging, patient
```

Choose what suits you.

#### Generate configuration

The wizard writes configuration files based on your answers. It shows you a preview -- read through it and confirm.

---

### Phase 4: Launch (~15 seconds)

The final phase brings everything together.

1. **Creates a welcome chat** -- a pre-written conversation starter with suggested prompts to help you explore what Apex can do.
2. **Starts the server** -- the Apex program begins running in the background.
3. **Opens your browser** -- a new tab or window opens automatically, pointed at your Apex instance.

```
Server is ready.
Opened https://localhost:8300 in your browser.
```

> **Do not close the Terminal window!** The server runs inside it. If you close Terminal, Apex stops. You can minimize the window instead.

> **Can I use my computer normally while Apex runs?** Yes! Apex uses very little resources while idle. Just don't close this specific Terminal window.

#### Want to run Apex without keeping Terminal open?

1. Open Terminal
2. Type: `cd ~/.apex && nohup bash server/launch.sh > /dev/null 2>&1 &`
3. You can now close Terminal — Apex keeps running

To stop it later: open Terminal and type `pkill -f apex.py`

---

## Step 3: Install Your Security Certificate

This step has a few more clicks than the others, but just follow along and you'll be fine.

### Why do I need to do this?

Remember those certificates the wizard generated in Phase 1? One of them (`client.p12`) is your browser's digital ID card. Your browser needs to present this ID to the Apex server every time it connects. Without it, the server refuses the connection.

This is much more secure than a password. Passwords can be guessed, leaked, or phished. A certificate is a unique digital file that only exists on your device.

You only need to do this once per browser.

> **What is Keychain Access?** Keychain Access is a built-in Mac app that stores passwords and certificates. Think of it like a secure vault on your computer. You will use it in the Safari steps below.

### Find the certificate file

The file you need is located at:

```
~/.apex/state/ssl/client.p12
```

**Not sure where the certificate file is?** In Terminal, type `open ~/.apex/state/ssl/` to open the folder in Finder.

You will also need the **password** that was shown during setup. If you chose the defaults, the password is: `apex`

---

### macOS -- Safari

Safari is the simplest browser to set up on Mac.

1. **Double-click** the `client.p12` file in Finder.
2. The **Keychain Access** app opens automatically. It asks which keychain to add it to. Leave the default ("login") selected and click **Add**.
3. Enter the certificate password (shown during setup, usually `apex`) and click **OK**.
4. The certificate is now in your keychain, but Safari will not trust it yet. Open **Keychain Access** (search for it with `Cmd + Space` if it is not already open).
5. In the sidebar, click **login** under "Default Keychains."
6. In the search bar at the top right, type **apex**.
7. You should see a certificate called **apex-client**. **Double-click** it.
8. Expand the **Trust** section by clicking the triangle next to it.
9. Change **"When using this certificate"** to **"Always Trust"**.
10. Close the window. It asks for your Mac login password -- enter it to confirm the change.

> **"I do not see the certificate in Keychain Access."** Make sure you are looking in the "login" keychain (left sidebar), not "System" or "System Roots." Also check the "My Certificates" category.

---

### macOS -- Chrome

**If you use Chrome on Mac, follow the Safari/Keychain steps above first.** Chrome reads from the same keychain, so once the certificate is installed for Safari, Chrome picks it up automatically.

Try going to `https://localhost:8300` — if Chrome asks you to pick a certificate, select the one labeled **apex-client** and you are done.

If Chrome does not find the certificate automatically:

1. Open Chrome and go to the address bar.
2. Type `chrome://settings/certificates` and press Enter.
3. This opens the certificate manager. Click **Your certificates** (or the relevant tab).
4. Click **Import**.
5. Navigate to `~/.apex/state/ssl/` and select `client.p12`.
6. Enter the certificate password and click **OK**.

---

### macOS -- Firefox

Firefox has its own certificate store, separate from the system keychain. You must import the certificate directly into Firefox.

1. Open Firefox.
2. Click the menu button (three horizontal lines in the top right) and go to **Settings**.
3. Search for "certificates" in the settings search bar, or scroll down to the **Privacy & Security** section.
4. Click **View Certificates**.
5. In the Certificate Manager window, click the **Your Certificates** tab.
6. Click **Import**.
7. Navigate to `~/.apex/state/ssl/` and select the `client.p12` file.
8. Enter the certificate password and click **OK**.

You should see the certificate appear in the list. Close the Certificate Manager.

---

### Linux -- Chrome / Chromium

1. Open Chrome and go to `chrome://settings/certificates`.
2. Click the **Your certificates** tab.
3. Click **Import**.
4. Select the `client.p12` file from `~/.apex/state/ssl/`.
5. Enter the certificate password.

### Linux -- Firefox

Follow the same steps as macOS Firefox above. The menus are in the same place.

---

## Step 4: Open Apex

Now the exciting part.

1. Open your browser.
2. Go to: **https://localhost:8300**
3. Your browser will ask which certificate to use. **Select the one you just installed** (it will be labeled something like "apex-client").

4. You should see the Apex chat interface.

> **Seeing a scary-looking warning from your browser?** This is expected and safe — it appears because you created the certificate yourself rather than getting one from a big company. Click **Advanced** (or **Show Details** in Safari), then click **Proceed to localhost** (or **visit this website**). It is completely safe for your own server.
>
> You may see this warning each time you open Apex in a new browser session. It's always safe to proceed.

---

## Step 5: Your First Chat

You are in! Here is what you are looking at:

- **The sidebar** on the left shows your conversations. You will see a "Welcome to Apex" chat already created.
- **The message area** in the center is where you type and read messages.
- **Suggested prompts** on the welcome screen give you ideas for things to try.

### Try it out

Click one of the suggested prompts, or type your own message and press Enter (or click the send button).

The AI responds using whichever model was configured during setup. If you connected Claude, it will use Claude. If you only set up a local model, it will use that.

**Some things to try:**

- "What can you do?" -- The AI explains its capabilities.
- "Scan my workspace and tell me what you find" -- The AI explores your files and summarizes what it sees.
- "Help me write a Python script that..." -- Give it a real task.
- Click the **+** button to create a new conversation.

> **Tip:** Each conversation is independent. The AI remembers context within a conversation, and the memory system carries knowledge across conversations over time.

---

## Step 6: (Optional) Build Your AI Team

Apex ships with six ready-to-use personas — Architect, Developer, Writer, Planner, Designer, and Assistant. Each one has a role, a model, and a personality tuned for a specific kind of work. Click **+** in the sidebar, pick a persona, and you have a specialist ready to go.

Every persona is fully customizable — change the model, name, avatar, role, and system prompt from the channel picker (hover any persona card, click the gear icon).

**Want to go deeper?** Read the full guide: **[Build Your AI Team](PERSONAS.md)**

### Group Channels — Multiple Agents, One Room

This is where Apex becomes something you can't get from ChatGPT, Claude, or any single-model tool. Put multiple agents in one channel and let them collaborate:

- **@mention routing** — tag a specific agent to direct your question
- **Agent-to-agent handoffs** — agents can pass tasks to each other
- **Parallel work** — multiple agents respond simultaneously

Create a Product Team, a Code Review Board, a Research Lab — whatever fits your workflow.

**Full guide: [Group Channels](GROUPS.md)**

> **You do not need personas or groups to use Apex.** They are optional ways to organize different types of work. Many people just use the default chat and are perfectly happy.

---

## Step 7: (Optional) Connect from Your Phone

You can access Apex from your iPhone or iPad over your local network. Your phone needs the same certificate your browser uses.

### iPhone / iPad

1. **Get the certificate file onto your phone.** The easiest way on Mac:
   - Open Finder and navigate to `~/.apex/state/ssl/` (in Terminal, type `open ~/.apex/state/ssl/` to open it).
   - AirDrop the `client.p12` file to your iPhone. (Right-click the file, choose **Share > AirDrop**, and select your phone.)
   - Alternatively, email it to yourself and open the attachment on your phone.

2. **Install the certificate.**
   - When you open the file on your iPhone, it will say "Profile Downloaded."
   - Go to **Settings > General > VPN & Device Management** (on older iOS versions, this may be called **Profiles** or **Profiles & Device Management**).
   - You will see the Apex certificate listed under "Downloaded Profile." Tap it.
   - Tap **Install** in the top right. Enter your iPhone passcode.
   - Tap **Install** again to confirm.

3. **Trust the certificate.**
   - Go to **Settings > General > About > Certificate Trust Settings**.
   - Find the Apex certificate and toggle it **on**.
   - Tap **Continue** on the warning.

4. **Connect to Apex.**
   - Open **Safari** on your phone.
   - Type your server's address: `https://YOUR-COMPUTER-IP:8300`
   - Replace `YOUR-COMPUTER-IP` with the IP address shown during setup (for example, `192.168.1.42`). To find your IP address again, open Terminal and type `ipconfig getifaddr en0` and press Enter.
   - Safari asks which certificate to use -- select the Apex certificate.
   - You should see the Apex chat interface.

> **"Can't connect" on your phone?** Make sure your phone and your computer are on the same Wi-Fi network. If they are on different networks, they cannot see each other.

> **ApexChat (native iOS app):** For a better mobile experience, the ApexChat iOS app provides push notifications, gesture navigation, and background streaming -- a native experience rather than a website in a browser. Connect it to your server the same way.

### Android

1. Transfer the `client.p12` file to your phone (email, file transfer, USB cable, etc.).
2. Go to **Settings > Security > Advanced > Encryption & Credentials > Install from storage**.
3. Select the `client.p12` file and enter the certificate password.
4. Open Chrome and navigate to `https://YOUR-COMPUTER-IP:8300`.

> **These menu paths may vary by manufacturer.** If you can't find the certificate settings, try searching "Install certificate" in your Settings search bar.

---

## Troubleshooting

Here are the most common issues people run into, and how to fix them.

### "This site can't be reached" or the page never loads

**The server is not running.** Open Terminal and start it:

```bash
cd ~/.apex
bash server/launch.sh
```

If you see an error about port 8300, see the next troubleshooting item.

### "Port 8300 already in use"

> **What is a port?** A port is like a numbered door on your computer that programs use to communicate. Port 8300 is the door Apex uses. This error means something else is already using that door (usually a previous Apex instance that did not shut down cleanly).

**First, try restarting your computer** — this clears any stuck processes and is the simplest fix.

If you prefer not to restart, you can stop the stuck program manually. Find what is using the port:
```bash
lsof -i :8300
```

This shows the program name and process ID. To stop it:
```bash
kill <process-id>
```

Replace `<process-id>` with the number shown in the PID column. This only stops that one program — it doesn't harm your computer or delete anything. Then try starting Apex again.

### "Certificate error" or "Your connection is not private"

This usually means one of two things:

1. **The certificate is not installed.** Go back to Step 3 and follow the instructions for your browser.
2. **The certificate is not trusted.** In Keychain Access (Mac), make sure you set the certificate to "Always Trust." In Firefox, make sure you imported it under "Your Certificates."

If all else fails, you can regenerate the certificates:
```bash
cd ~/.apex && .venv/bin/python3 setup.py --regen-certs
```

Then re-import the new `client.p12` into your browser.

### The browser does not ask me to select a certificate

This means the certificate was not imported correctly, or it was imported into the wrong certificate store.

- **Safari/Chrome on Mac:** The certificate must be in your **login keychain** in Keychain Access.
- **Firefox:** The certificate must be imported into Firefox's own certificate manager (it does not use the system keychain).
- **Try restarting your browser** after importing the certificate.
- **Re-import:** Delete the old certificate and import `client.p12` again, making sure to enter the correct password.

### Installer fails on dependencies

If `install.sh` fails during package installation, it usually means Python is too old or missing build tools.

Check your Python version:
```bash
python3 --version
```

You need version 3.10 or newer. If you see an older version or "command not found":

- Go to [python.org/downloads](https://www.python.org/downloads/)
- Download and install the latest version
- Close and reopen Terminal
- Run `bash install.sh` again from `~/.apex`

### The AI says it cannot access my files

The workspace path might be wrong. Check it by going to the dashboard (**https://localhost:8300/admin**) and looking at the Workspace section. Make sure it points to the folder you want the AI to work with.

### I want to start over

Run the installer again:
```bash
cd ~/.apex
bash install.sh
```

Or re-run just the setup wizard:
```bash
cd ~/.apex
.venv/bin/python3 setup.py
```

It detects the previous setup and offers a menu. Choose **"Run full setup again"** to start fresh.

---

## What's Next?

Now that Apex is running, here are some things to explore:

- **[Build Your AI Team](PERSONAS.md)** -- set up specialized personas for different kinds of work.
- **[Group Channels](GROUPS.md)** -- put multiple agents in one room and let them collaborate on tasks together.
- **The Dashboard** at `https://localhost:8300/admin` -- manage settings, models, certificates, and more from a web interface.
- **Skills** -- type `/help` in a chat to see available slash commands. Try `/recall` to search your conversation history or `/first-principles` for deep analysis.
- **Memory** -- the more you use Apex, the more it remembers about your work. Over time, it gets better at helping you because it builds up knowledge about your projects and preferences.
- **Multiple models** -- create different conversations for different AI models. Use Claude for deep work, Grok for web research, and a local model for quick questions.

---

## Getting Help

- **Troubleshooting guide:** See `docs/TROUBLESHOOTING.md` in the Apex folder for a detailed log of known issues and fixes.
- **GitHub Issues:** Report bugs or ask questions at [github.com/use-ash/apex/issues](https://github.com/use-ash/apex/issues).
- **Re-run setup:** `cd ~/.apex && .venv/bin/python3 setup.py` -- the wizard detects your existing configuration and offers options to update specific parts without starting over.

---

## Quick Reference

| What | How |
|------|-----|
| Install location | `~/.apex` |
| Start Apex | `cd ~/.apex && bash server/launch.sh` |
| Stop Apex | Close the Terminal window, or press Ctrl+C |
| Apex URL | https://localhost:8300 |
| Admin Dashboard | https://localhost:8300/admin |
| Virtual environment | `~/.apex/.venv/` |
| Your data | `~/.apex/state/` |
| API keys | `~/.apex/.env` |
| Logs | `~/.apex/state/apex.log` |
| Re-run setup | `cd ~/.apex && .venv/bin/python3 setup.py` |

---

## Uninstalling

To remove Apex:

```bash
cd ~/.apex
.venv/bin/python3 setup.py --uninstall
```

This preserves your memory files and conversation history. To remove everything:

```bash
cd ~/.apex
.venv/bin/python3 setup.py --uninstall --purge
```

---

*You made it. Welcome to Apex.*
