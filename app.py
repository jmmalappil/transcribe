import streamlit as st
import moviepy.editor as mp
from pydub import AudioSegment
from google.cloud import speech, texttospeech
import json
import io
import os
import requests

def extract_audio(video_file, audio_file):
    video = mp.VideoFileClip(video_file)
    video.audio.write_audiofile(audio_file)

def convert_to_mono(input_audio, output_audio):
    sound = AudioSegment.from_file(input_audio)
    sound = sound.set_channels(1)  # Convert to mono
    sound.export(output_audio, format="wav")

def audio_to_text(audio_file):
    client = speech.SpeechClient()

    # Load audio file
    with io.open(audio_file, "rb") as audio:
        content = audio.read()
    audio = speech.RecognitionAudio(content=content)

    # Configure recognition
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=44100,
        language_code="en-US",
    )

    # Recognize speech in audio file
    response = client.recognize(config=config, audio=audio)

    # Extract transcription
    transcript = ""
    for result in response.results:
        transcript += result.alternatives[0].transcript + "\n"
    return transcript

def correct_transcription_azure(transcript, azure_endpoint, azure_api_key):
    try:
        headers = {
            "Content-Type": "application/json",
            "api-key": azure_api_key
        }

        data = {
            "messages": [
                {"role": "user", "content": f"Correct the following transcription by removing filler words like 'um', 'hmm', etc., and fixing grammatical mistakes: {transcript}"}
            ],
            "max_tokens": 500
        }

        response = requests.post(azure_endpoint, headers=headers, json=data)

        if response.status_code == 200:
            result = response.json()
            corrected_transcript = result["choices"][0]["message"]["content"].strip()
            return corrected_transcript
        else:
            st.error(f"Failed to connect or retrieve response: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        st.error(f"Failed to connect or retrieve response: {str(e)}")
        return None

def text_to_speech_google(text, output_audio_file):
    client = texttospeech.TextToSpeechClient()

    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Build the voice request, select the language code and the 'Journey' voice model
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Wavenet-J"
    )

    # Select the type of audio file you want returned
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )

    # Perform the text-to-speech request on the text input
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    # Write the output to the audio file
    with open(output_audio_file, "wb") as out:
        out.write(response.audio_content)

def replace_audio_in_video(video_file, new_audio_file, output_video_file):
    video = mp.VideoFileClip(video_file)
    new_audio = mp.AudioFileClip(new_audio_file)


    # Adjust audio duration to match video duration
    if new_audio.duration > video.duration:
        new_audio = new_audio.subclip(0, video.duration)
    elif new_audio.duration < video.duration:
        silence = AudioSegment.silent(duration=(video.duration - new_audio.duration) * 1000)
        new_audio = AudioSegment.from_file(new_audio_file) + silence
        new_audio.export(new_audio_file, format="wav")
        new_audio = mp.AudioFileClip(new_audio_file)
    
    # Set start time to sync audio and video better
    video_duration = video.duration
    audio_duration = new_audio.duration
    sync_start_time = 0

    if audio_duration > video_duration:
        sync_start_time = (audio_duration - video_duration) / 2
        new_audio = new_audio.subclip(sync_start_time, sync_start_time + video_duration)
    else:
        sync_start_time = (video_duration - audio_duration) / 2
        video = video.subclip(sync_start_time, sync_start_time + audio_duration)

    video = video.set_audio(new_audio)
    # Explore using different codecs or additional settings to ensure the audio and video sync seamlessly, possibly with guidance from a media processing specialist.
    video.write_videofile(output_video_file, codec="libx264", audio_codec="aac", 
                          temp_audiofile='temp-audio.m4a', remove_temp=True, threads=4, preset='ultrafast')

# Streamlit App
st.title("Video to Text Transcription")

# Load the credentials from the environment variable
credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')

if credentials_json:
    credentials_dict = json.loads(credentials_json)

    # Write the credentials to a temporary file
    with open("/tmp/google_credentials.json", "w") as cred_file:
        cred_file.write(json.dumps(credentials_dict))

    # Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to point to the temporary file
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = "/tmp/google_credentials.json"

# Azure API credentials
azure_api_key = "22ec84421ec24230a3638d1b51e3a7dc"
azure_endpoint = "https://internshala.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-08-01-preview"

# Upload video file
uploaded_file = st.file_uploader("Upload a video file", type=["mp4", "mkv", "avi", "mov"])

if uploaded_file is not None:
    # Save uploaded video file
    video_path = "uploaded_video.mp4"
    with open(video_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success("Video file uploaded successfully!")

    # Extract audio from video
    extracted_audio = "extracted_audio.wav"
    extract_audio(video_path, extracted_audio)
    st.success("Audio extracted from video!")

    # Convert extracted audio to mono
    mono_audio = "mono_audio.wav"
    convert_to_mono(extracted_audio, mono_audio)
    st.success("Audio converted to mono!")

    # Convert audio to text
    try:
        transcript = audio_to_text(mono_audio)
        st.subheader("Transcription:")
        st.text_area("", value=transcript, height=300)

        # Correct transcription using Azure API
        if azure_endpoint and azure_api_key:
            corrected_transcript = correct_transcription_azure(transcript, azure_endpoint, azure_api_key)
            st.subheader("Corrected Transcription:")
            st.text_area("", value=corrected_transcript, height=300)

            # Convert corrected text to speech using Google Text-to-Speech
            corrected_audio = "corrected_audio.wav"
            text_to_speech_google(corrected_transcript, corrected_audio)
            st.success("Text converted to speech!")

            # Replace audio in the original video
            output_video = "output_video.mp4"
            replace_audio_in_video(video_path, corrected_audio, output_video)
            st.success("Audio replaced in video!")

            # Provide download link for the final video
            with open(output_video, "rb") as f:
                btn = st.download_button(
                    label="Download Final Video",
                    data=f,
                    file_name=output_video,
                    mime="video/mp4"
            )
    except Exception as e:
        st.error(f"An error occurred during transcription: {e}")

    
