import pydub

import argparse
import os
import datetime
import shutil


def main():
    arg_parser = init_arg_parser()
    args = arg_parser.parse_args()

    wave_file_list = []
    task_list = []
    _dir = '.'
    backup_dir = ''
    peak_db = -12

    if args.directory:
        _dir = str((args.directory[0]))

        for file in os.listdir(_dir):
            if file.endswith('.wav'):
                wave_file_list.append(file)

    if args.file:
        file_name = args.file[0]
        wave_file_list.append(file_name)

    if args.backup:
        task_list.append('_BACKUP')

        if args.backup == 'DefBackupDir':
            current_date = datetime.datetime.strftime(
                datetime.datetime.now(),
                '%Y-%m-%d %H:%M'
            )

            backup_dir = 'Stems Backup ' + current_date

        else:
            backup_dir = args.backup[0]


    if args.splitstereo:
        task_list.append('_SPLIT-STEREO')

    if args.gainstage:
        task_list.append('_GAINSTAGE')
        peak_db = int(args.gainstage)

        if peak_db > 0:
            if question_y_or_n('You\'ve selected a peak above 0 dB which may cause clipping. Continue?',
                               n_dominant=True):
                pass

            else:
                return 0

    perform_tasks(task_list, wave_file_list, _dir, backup_dir, peak_db)


def perform_tasks(task_list, wave_file_list, _dir, backup_dir, peak_db=-12):
    if '_BACKUP' in task_list:
        print('Saving backup in directory "{}".'.format(backup_dir))
        backup_files(wave_file_list, _dir, backup_dir)
        print()

    if '_SPLIT-STEREO' in task_list:
        print('Splitting stereo files.')
        wave_file_list = split_stereo_files(wave_file_list)
        print()

    if '_GAINSTAGE' in task_list:
        print('Gain staging with {} dB as peak amplitude.'.format(peak_db))
        change_peak_db(wave_file_list, peak_db)


def backup_files(wave_file_list, _dir, backup_dir):
    os.mkdir(backup_dir)

    for wave_file in wave_file_list:
        shutil.copy2(wave_file, '{}/{}'.format(backup_dir, wave_file))


def change_peak_db(wave_file_list, peak_db):
    for wave_file in wave_file_list:
        audio_file = pydub.AudioSegment.from_file(wave_file)
        peak_amplitude = get_peak_db(wave_file)

        reduction_gain = peak_amplitude - peak_db
        audio_file = audio_file - reduction_gain


        audio_file.export(wave_file, format='wav')

        print('[{}] {} dB ----> {} dB'.format(wave_file, round(peak_amplitude), round(get_peak_db(wave_file))))


def get_peak_db(file_name):
    audio_file = pydub.AudioSegment.from_file(file_name)
    return audio_file.max_dBFS


def split_stereo_files(wave_file_list):
    new_wave_file_list = []

    for wave_file in wave_file_list:
        segment = pydub.AudioSegment.from_file(wave_file)
        wavef_no_ext = wave_file[:-4]

        if segment.channels == 1:
            pass

        else:
            mono_segments = segment.split_to_mono()
            left_channel = mono_segments[0]
            right_channel = mono_segments[1]

            left_channel.export('{} L.wav'.format(wavef_no_ext), format='wav')
            right_channel.export('{} R.wav'.format(wavef_no_ext), format='wav')

            new_wave_file_list.append('{} L.wav'.format(wavef_no_ext))
            new_wave_file_list.append('{} R.wav'.format(wavef_no_ext))

            wave_file_list.remove(wave_file)
            os.remove(wave_file)
    
            print('[{}] ----> [{} L.wav] + [{} R.wav]'.format(wave_file, wavef_no_ext, wavef_no_ext))

    new_wave_file_list.extend(wave_file_list)
    return new_wave_file_list


def question_y_or_n(question, y_dominant=True, n_dominant=False):
    if n_dominant:
        y_dominant = False

    yes_response = ['y', 'yes', 'ye']
    no_response = ['n', 'no']

    if y_dominant:
        yes_response.append('')
        print(question + ' [Y/n]')

    else:
        no_response.append('')
        print(question + ' [y/N]')

    user_choice = input().lower()

    if user_choice in yes_response:
        return True

    else:
        return False


def init_arg_parser():
    parser = argparse.ArgumentParser(
        description='Performs operations on wave files in preparation for mixing.'
    )

    parser.add_argument(
        '-g',
        '--gainstage',
        nargs='?',
        const=-12,
        type=int,
        help='Sets peak dB (-12 dB if not specified)'
    )

    parser.add_argument(
        '-s',
        '--splitstereo',
        action='store_true',
        help='Splits stereo files into separate mono tracks (L/R)'
    )

    parser.add_argument(
        '-f',
        '--file',
        nargs=1,
        help='Select individual file'
    )

    parser.add_argument(
        '-d',
        '--directory',
        nargs=1,
        help='Directory to search for wave files (working directory if not specified)'
    )

    parser.add_argument(
        '-b',
        '--backup',
        nargs='?',
        const='DefBackupDir',
        type=str,
        help='Backup files before overwriting with changes (Creates folder in working directory if not specified)'
    )

    return parser

if __name__ == '__main__':
    main()
