# This script extracts the data from midi files
import sys, os
import pandas as pd
import music21
import re

input_midi = sys.argv[1]
translated_midi = music21.midi.translate.midiFilePathToStream(input_midi)

# creating list from objects contained in translated_midi
parts_list = [item for item in translated_midi]

# checking for substreams
substreams_check = {}
counter = 0
for part in parts_list:
    substreams_check[counter] = False
    for item in part:
        if 'stream' in str(item):
            substreams_check[counter] = True
            break
    counter += 1

# adding all music streams
list_of_streams = []
for key in substreams_check.keys():   
    if substreams_check[key] == True:
        for item in parts_list[key]:
            if 'stream' in str(item):
                list_of_streams.append(item)
    else:
        list_of_streams.append(parts_list[key])

list_of_streams

# preparing dictionary with soon-to-be data frames per stream
streams = {}
for instrument in range(len(list_of_streams)):
    streams[instrument] = {'type': [],
                           'name': [],
                           'pitch_midi_value': [],
                           'duration_name': [],
                           'duration_value': []}

# adding values to streams dictionary
for instrument in range(len(list_of_streams)):
    for note_loc in range(len(list_of_streams[instrument])):
        if (type(list_of_streams[instrument][note_loc]) == music21.note.Note) & (list_of_streams[instrument][note_loc].duration.quarterLength != 0):
            streams[instrument]['type'].append('note')
            streams[instrument]['name'].append(list_of_streams[instrument][note_loc].name)
            streams[instrument]['pitch_midi_value'].append(list_of_streams[instrument][note_loc].pitch.midi)
            streams[instrument]['duration_name'].append(list_of_streams[instrument][note_loc].duration.fullName)
            streams[instrument]['duration_value'].append(list_of_streams[instrument][note_loc].duration.quarterLength)
        elif (type(list_of_streams[instrument][note_loc]) == music21.chord.Chord) & (list_of_streams[instrument][note_loc].duration.quarterLength != 0):
            streams[instrument]['type'].append('chord')
            streams[instrument]['name'].append(tuple(list_of_streams[instrument][note_loc].pitchNames))
            streams[instrument]['pitch_midi_value'].append(tuple(p.midi for p in list_of_streams[instrument][note_loc].pitches))
            streams[instrument]['duration_name'].append(list_of_streams[instrument][note_loc].duration.fullName)
            streams[instrument]['duration_value'].append(list_of_streams[instrument][note_loc].duration.quarterLength)

# creating data frames
dataframes = {}
for key in streams.keys():
    dataframes[key] = pd.DataFrame(streams[key])

# creating midi for each instrument in list_of_streams
midi_dict = {}
for item_position in range(len(list_of_streams)):
    midi_dict[item_position] = music21.midi.translate.streamToMidiFile(list_of_streams[item_position])

# converting midi contents to string for parsing
midi_string = {}
for key in midi_dict.keys():
    midi_string[key] = str(midi_dict[key])

# regex'd list of items from midi_string's
regex = {}
for key in midi_string.keys():
    regex[key] = re.findall('<(.[^>]*)', midi_string[key])

# extracting velocities from NOTE_ON MidiEvents
velocities = {}
for key in midi_string.keys():
    regex_velocities = pd.Series(re.findall('velocity=(.[^>]*)', midi_string[key]))
    on_off_booleans = [True if status == 'NOTE_ON' else False for status in re.findall('NOTE_O[NF]F?', midi_string[key])]
    velocities[key] = list(regex_velocities[on_off_booleans])

# creating list numbers corresponding to how many notes per rest/note/chord
for key in dataframes.keys():
    list_of_note_numbers = []
    for i in dataframes[key].index:
        if dataframes[key].iloc[i, 0] == 'note':
            list_of_note_numbers.append(1)
        else:
            list_of_note_numbers.append(len(dataframes[key].iloc[i, 1]))

# appending number of velocity values equal to number of notes per rest/note/chord  
    position = 0
    list_of_velocity_lists = []
    for number in list_of_note_numbers:
        if number == 1:
            list_of_velocity_lists.append(velocities[key][position])
        else:
            list_of_velocity_lists.append(tuple(velocities[key][position:position + number]))
        position += number

    dataframes[key]['velocity'] = list_of_velocity_lists

# adding values for all implicit rest times occuring before notes are played
# adding values for start time of each note
for key in dataframes.keys():
    list_of_implicit_rest_times = []
    counter = 0
    for i in range(len(dataframes[key]['pitch_midi_value'])):
        if i == 0:
            previous_note_duration = 0
        else:
            previous_note_duration = dataframes[key]['duration_value'][i-1]           
        pitch = dataframes[key]['pitch_midi_value'][i]
        if type(pitch) == tuple:
            pitch = pitch[0]
        implicit_rest_time = 0
        for j in range(counter, len(regex[key])):
            if (('NOTE_ON' in regex[key][j]) & (f'pitch={pitch}' in regex[key][j])):
                implicit_rest_time = abs(implicit_rest_time - previous_note_duration)
                list_of_implicit_rest_times.append(implicit_rest_time)
                counter = j + 1
                break
            if ('DeltaTime' in regex[key][j]):
                implicit_rest_time += music21.midi.translate.midiToDuration(re.findall('t=(\d\d?\d?\d?\d?)', regex[key][j])[0]).quarterLength

    dataframes[key]['prior_rest_time'] = list_of_implicit_rest_times
    dataframes[key]['start_time'] = dataframes[key]['prior_rest_time'].cumsum() + dataframes[key]['duration_value'].shift(1).fillna(0).cumsum()

# exporting dataframes and retranslated midi files, making output directories where necessary
if os.path.isdir(input_midi.split('/')[0]) == True:
    name = input_midi.replace(' ', '_').replace('.mid', '').split('/')[-1]
else:
    name = input_midi.replace(' ', '_').replace('.mid', '')

if os.path.isdir("./output_data_frames") == False:
    os.mkdir('./output_data_frames')
for key in dataframes.keys():
    dataframes[key]['song'] = name
    dataframes[key]['stream'] = key  
    column_arrangement = ['song', 'stream', 'type', 'name', 'pitch_midi_value', 'velocity', 'duration_name', 'duration_value', 'prior_rest_time', 'start_time']
    dataframes[key] = dataframes[key].reindex(columns=column_arrangement)
    dataframes[key].to_csv(f'output_data_frames/df_{key}___{name}.csv', index=False)

if os.path.isdir("./output_midi_files") == False:
    os.mkdir('./output_midi_files')
for key in midi_dict.keys():
    midi_dict[key].open(f'output_midi_files/midi_{key}___{name}.mid', 'wb')
    midi_dict[key].write()
    midi_dict[key].close()