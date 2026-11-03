#!/usr/bin/env python3
"""Master the narration and mux it with the picture.

usage: mix.py VOICE PICTURE.mp4 OUT.mp4
"""
import json, re, subprocess, sys

voice_in, picture, out = sys.argv[1:4]
chain = "highpass=f=70,equalizer=f=250:t=q:w=1.2:g=-1.5,equalizer=f=3200:t=q:w=1.5:g=1.2,acompressor=threshold=-22dB:ratio=2:attack=12:release=160:makeup=1"
stats = subprocess.run(["ffmpeg", "-hide_banner", "-i", voice_in, "-af", f"{chain},loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
m = json.loads(re.search(r"\{[^{}]*input_i[^{}]*\}", stats, re.S).group(0))
vf = (f"{chain},loudnorm=I=-16:TP=-1.5:LRA=7:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
      f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']},aresample=48000")
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", picture, "-i", voice_in, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", vf,
                "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-movflags", "+faststart", out], check=True)
print("mixed", out)
