from ...path import pathtool, AudioFile


@pathtool(input="audio_path", output="return")
def denoise(audio_path: AudioFile, output_path: AudioFile) -> AudioFile:
    """Remove noise from audio file and return multiple outputs
    
    Args:
        audio_path(required): The path to the audio file to denoise
        output_path: The path to the output audio file

    Returns:
        The path to the output audio file
    """
    from time import time
    import_time = time()
    from modelscope.pipelines import pipeline
    from modelscope.utils.constant import Tasks
    after_import_time = time()
    print(f"Import time: {after_import_time - import_time} seconds")
    model_path = 'iic/speech_zipenhancer_ans_multiloss_16k_base'
    denoise_model = pipeline(
        Tasks.acoustic_noise_suppression,
        model=model_path)
    after_model_time = time()
    print(f"Model time: {after_model_time - after_import_time} seconds")
    start_time = time()
    result = denoise_model(audio_path, output_path=output_path)
    after_denoise_time = time()
    print(f"Denoise time: {after_denoise_time - start_time} seconds")
    for key, value in result.items():
        # Convert value to string and truncate if longer than 50 chars
        value_str = str(value)
        if len(value_str) > 50:
            value_str = value_str[:47] + "..."
        print(f"{key}: {value_str}")
    return output_path