"""Builds the demo soundtrack: neural-TTS voiceover (edge-tts) + an original synthesized score
(warm pads / sub bass / pluck arp / soft kick) + SFX (impact / whoosh / ding / riser), mixed with
music ducked under the VO, then muxed onto video/out/g4studio-demo.mp4 -> video/g4studio-demo.mp4.

Run from the repo root after rendering the video:  python video/build_audio.py
Requires: edge-tts (pip install edge-tts), scipy, numpy, ffmpeg on PATH.
Scene start times below must match the Sequence offsets in src/Video.tsx (30 fps).
"""
import os, subprocess, numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100; T = 54.0; N = int(T * SR)
HERE = os.path.dirname(os.path.abspath(__file__))
AUD = os.path.join(HERE, "audio"); os.makedirs(AUD, exist_ok=True)
VOICE = "en-US-AvaMultilingualNeural"

# (voiceover line, start-time in seconds) — start times track the scene cuts in Video.tsx
VO = [
    ("G4 Studio. Roblox, as a robot data factory.", 0.3),
    ("Robot learning needs demonstration data, and it's slow to collect. So we made collecting it a game.", 4.7),
    ("A faithful S O 101 arm, rebuilt from the official U R D F, with real inverse kinematics.", 11.2),
    ("Gemma 4, running on Cerebras, invents fun games where playing them is labeling the data.", 19.2),
    ("Every playthrough becomes a labeled demonstration. 192 episodes, from real human play.", 25.8),
    ("It's recorded in the arm's native joint space, and exported to LeRobot. And it's learnable: the policy recovers the actions almost perfectly.", 32.8),
    ("Point it at any robot. One command derives the kinematics from a U R D F, in minutes.", 42.4),
    ("G4 Studio. Play becomes the data that teaches robots.", 49.4),
]

def sh(c): subprocess.run(c, shell=True, capture_output=True)

# ---- neural TTS ----
for i, (text, _) in enumerate(VO):
    mp3 = f"{AUD}/vo_{i}.mp3"; wav = f"{AUD}/vo_{i}.wav"
    sh(f'python -m edge_tts --voice {VOICE} --rate "+6%" --text "{text}" --write-media "{mp3}"')
    sh(f'ffmpeg -y -i "{mp3}" -ar {SR} -ac 1 "{wav}"')

# ---- dsp helpers ----
def lp(x, fc): b, a = signal.butter(2, fc/(SR/2), "low"); return signal.lfilter(b, a, x)
def bp(x, f1, f2): b, a = signal.butter(2, [f1/(SR/2), f2/(SR/2)], "band"); return signal.lfilter(b, a, x)
def sine(f, n): return np.sin(2*np.pi*f*np.arange(n)/SR)
def saw(f, n): return signal.sawtooth(2*np.pi*f*np.arange(n)/SR)
def adsr(n, a, d, s, r):
    e = np.ones(n); ai, di, ri = int(a*SR), int(d*SR), int(r*SR)
    if ai: e[:ai] = np.linspace(0, 1, ai)
    if di: e[ai:ai+di] = np.linspace(1, s, di)
    e[ai+di:max(ai+di, n-ri)] = s
    if ri and n-ri > 0: e[n-ri:] = np.linspace(s, 0, ri)
    return e
def place(buf, clip, t0):
    i = int(t0*SR)
    if i >= len(buf) or i < 0: return
    j = min(len(buf), i+len(clip))
    if j > i: buf[i:j] += clip[:j-i]

# ---- score: Am - F - C - G, energetic — 124 BPM, four-on-floor + hats + plucked bass + 16th arp ----
BPM = 124; BEAT = 60/BPM; BAR = 4*BEAT
prog = [(110.0, [220.0, 261.63, 329.63]), (87.31, [174.61, 220.0, 261.63]),
        (130.81, [196.0, 261.63, 329.63]), (98.0, [196.0, 246.94, 293.66])]
def pad(freqs, dur):
    n = int(dur*SR); o = np.zeros(n)
    for f in freqs:
        for det in (-0.08, 0.0, 0.08): o += saw(f*2**(det/12), n)
    return lp(o*adsr(n, 0.18, 0.2, 0.85, 0.4), 2200)/(len(freqs)*3)
def pluck(f, dur):
    n = int(dur*SR); return lp((sine(f, n)+0.5*sine(2*f, n))*np.exp(-np.arange(n)/SR*9.0), 3200)
def kick(dur=0.30):
    n = int(dur*SR); t = np.arange(n)/SR; fr = 165*np.exp(-t*30)+50
    body = np.sin(2*np.pi*np.cumsum(fr)/SR)*np.exp(-t*7.5)
    click = np.exp(-t*190)*np.sign(np.sin(2*np.pi*1800*t))*0.3
    return body+click
def hat(dur=0.05, op=False):
    n = int(dur*SR); t = np.arange(n)/SR
    return bp(np.random.randn(n), 6500, 15000)*np.exp(-t*(14 if op else 45))
def bass(f, dur=0.22):
    n = int(dur*SR); return lp((saw(f, n)*0.6+sine(f, n))*np.exp(-np.arange(n)/SR*9.0), 1100)
def bell(f, dur=1.3):
    n = int(dur*SR); t = np.arange(n)/SR; return (sine(f, n)+0.5*sine(2.01*f, n)+0.3*sine(3*f, n))*np.exp(-t*3)
music = np.zeros(N); t = 0.0; bar = 0
while t < T:
    sub, tr = prog[bar % 4]
    place(music, pad(tr, BAR)*0.12, t)
    place(music, sine(sub, int(BAR*SR))*adsr(int(BAR*SR), 0.04, 0.1, 0.85, 0.3)*0.16, t)
    if bar >= 2:  # the beat drops after a short atmospheric intro
        for b in range(4): place(music, kick()*0.66, t+b*BEAT)                      # four-on-floor
        for k in range(8): place(music, hat(0.05, op=(k % 2 == 1))*(0.16 if k % 2 else 0.09), t+k*BEAT/2)
        for bt in (0.0, 0.5, 1.5, 2.0, 2.5, 3.5): place(music, bass(sub*2)*0.24, t+bt*BEAT)  # syncopated bass
        notes = tr+[tr[2]*2, tr[1], tr[2], tr[0]*2]
        for k in range(16): place(music, pluck(notes[k % len(notes)], 0.16)*0.06, t+k*BEAT/4)  # 16th arp
        place(music, bell(tr[2]*2)*0.05, t)
    t += BAR; bar += 1
rv = music.copy()
for dl, g in [(0.09, 0.28), (0.17, 0.20), (0.27, 0.12)]:
    d = int(dl*SR); pp = np.zeros(len(music)); pp[d:] = music[:-d]; rv += pp*g
music = lp(rv, 7000)
env = np.ones(N); fin, fout = int(1.4*SR), int(3.0*SR)
env[:fin] = np.linspace(0, 1, fin); env[-fout:] = np.linspace(1, 0, fout); music *= env

# ---- sfx ----
def whoosh(dur=0.6): n = int(dur*SR); return bp(np.random.randn(n), 300, 4000)*np.sin(np.linspace(0, np.pi, n))**1.5
def ding(f=880, dur=0.7):
    n = int(dur*SR); e = np.exp(-np.arange(n)/SR*5); return (sine(f, n)+0.5*sine(2*f, n)+0.3*sine(3*f, n))*e
def impact(dur=1.2):
    n = int(dur*SR); t = np.arange(n)/SR; fr = 90*np.exp(-t*8)+40
    return np.sin(2*np.pi*np.cumsum(fr)/SR)*np.exp(-t*3.5)+0.25*bp(np.random.randn(n), 60, 500)*np.exp(-t*5)
def riser(dur=1.6):
    n = int(dur*SR); t = np.arange(n)/SR; f = np.linspace(200, 1800, n); return np.sin(2*np.pi*np.cumsum(f)/SR)*(t/dur)**2
sfx = np.zeros(N); place(sfx, impact()*0.45, 0.05)
for tt in [4.5, 11.0, 19.0, 25.6, 32.6, 42.2, 49.2]: place(sfx, whoosh()*0.22, tt-0.25)
for tt, f in [(26.0, 784), (26.5, 988), (27.0, 1175)]: place(sfx, ding(f)*0.14, tt)
for tt in [33.6, 34.0, 34.4, 34.8, 35.2, 35.6]: place(sfx, ding(1320, 0.4)*0.06, tt)
place(sfx, riser()*0.18, 47.6); place(sfx, impact()*0.4, 49.3)

# ---- voiceover + sidechain duck ----
vo = np.zeros(N); duck = np.ones(N)
for i, (_, t0) in enumerate(VO):
    _, d = wavfile.read(f"{AUD}/vo_{i}.wav"); d = d.astype(np.float32); d /= max(1, np.abs(d).max())
    place(vo, d*0.95, t0)
    a = int(t0*SR); b = min(N, a+len(d)+int(0.3*SR)); duck[a:b] = 0.42
duck = lp(duck, 12.0)
mix = music*duck + vo + sfx; mix /= max(1.001, np.abs(mix).max()/0.97)
wavfile.write(f"{AUD}/mix.wav", SR, (mix*32767).astype(np.int16))

# ---- mux ----
vid = os.path.join(HERE, "out", "g4studio-demo.mp4"); out = os.path.join(HERE, "g4studio-demo.mp4")
sh(f'ffmpeg -y -i "{vid}" -i "{AUD}/mix.wav" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -shortest "{out}"')
print("wrote", out)
