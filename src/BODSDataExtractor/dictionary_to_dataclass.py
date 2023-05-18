import pandas as pd
from dacite import from_dict
import xmltodict
import datetime
from classes import *


def extract_timetable_operating_days(days):
    ''' Ensuring the operating days are ordered appropriately '''

    operating_day_list = list(days)

    # adding dictionary variables and values to "day" dictionary

    day = {}
    day['Monday'] = 1
    day['Tuesday'] = 2
    day['Wednesday'] = 3
    day['Thursday'] = 4
    day['Friday'] = 5
    day['Saturday'] = 6
    day['Sunday'] = 7

    brand_new = {}

    # checking if the day of the week is in the above dictionary so we can sort the days
    for i in operating_day_list:
        if i in day:
            brand_new.update({i: day[i]})

        # sorting the days of operation
    sortit = sorted(brand_new.items(), key=lambda x: x[1])

    length = len(sortit)

    operating_days = ""

    consecutive = True

    # checking to see if the days in the list are not consective

    for i in range(length - 1):
        if sortit[i + 1][1] - sortit[i][1] != 1:
            consecutive = False
            break

    # if there are no days of operation entered
    if length == 0:
        operating_days = "None"

    # if there is only one day of operation
    elif length == 1:
        operating_days = sortit[0][0]

        # if the operating days are not consecutive, they're seperated by commas
    elif not consecutive:
        for i in range(length):
            operating_days = operating_days + sortit[i][0] + ","

        # if consecutive, operating days are given as a range
    else:
        # print(sortit)
        operating_days = sortit[0][0] + "-" + sortit[-1][0]

    return operating_days


def extract_runtimes(vj, journey_pattern_timing_link, vjtl_index):

    """Extract the runtimes from timing links as a string. If JPTL run time is 0, VJTL will be checked"""

    # extract run times from jptl
    runtime = journey_pattern_timing_link.RunTime

    # if jptl runtime is 0, find equivalent vehicle journey pattern timing link run time
    if pd.Timedelta(runtime).value == 0:

        if vj.VehicleJourneyTimingLink is not None:

            runtime = vj.VehicleJourneyTimingLink[vjtl_index[journey_pattern_timing_link.id]].RunTime

            return runtime

    return runtime


def extract_common_name(stop_object,StopPointRef, stop_point_index):
    """Extract information about the name of the stop including longitude and latitude"""

    stop_common_name = stop_object.AnnotatedStopPointRef[stop_point_index[StopPointRef]].CommonName
    stop_location = stop_object.AnnotatedStopPointRef[stop_point_index[StopPointRef]].Location

    if not stop_location:
        stop_lat = "-"
        stop_long = "-"

    else:
        stop_lat = stop_object.AnnotatedStopPointRef[stop_point_index[StopPointRef]].Location.Latitude
        stop_long = stop_object.AnnotatedStopPointRef[stop_point_index[StopPointRef]].Location.Longitude

    return stop_common_name, stop_lat, stop_long


def next_jptl_in_sequence(jptl, vj_departure_time, vj, vjtl_index,stop_object, stop_point_index, first_jptl=False):
    """Returns the sequence number, stop point ref and time for a JPTL to be added to a outboud or inbound df"""

    runtime = extract_runtimes(vj, jptl, vjtl_index)
    common_name, latitude, longitude = extract_common_name(stop_object, str(jptl.To.StopPointRef), stop_point_index)

    to_sequence = [int(jptl.To.sequence_number),
                   str(jptl.To.StopPointRef),
                   latitude,
                   longitude,
                   str(common_name),
                   pd.Timedelta(runtime)]

    if first_jptl:
        common_name, latitude, longitude = extract_common_name(stop_object,jptl.From.StopPointRef, stop_point_index)

        from_sequence = [int(jptl.From.sequence_number),
                         str(jptl.From.StopPointRef),
                         latitude,
                         longitude,
                         str(common_name),
                         vj_departure_time]

        return from_sequence, to_sequence

    if not first_jptl:
        return to_sequence


def collate_vjs(direction_df, collated_timetable):
    """Combines all vehicle journeys together for inbound or outbound"""

    if direction_df.empty:
        pass
    elif collated_timetable.empty:
        # match stop point ref + sequence number with the initial timetable's stop point ref+sequence number
        collated_timetable = collated_timetable.merge(direction_df, how='outer', left_index=True, right_index=True)
    else:
        # match stop point ref + sequence number with the initial timetable's stop point ref+sequence number
        collated_timetable = pd.merge(direction_df, collated_timetable, on=["Sequence Number",
                                                                            'Stop Point Ref',
                                                                            "Latitude",
                                                                            "Longitude",
                                                                            "Common Name"],
                                      how='outer',
                                      validate='1:m').fillna("-")

    return collated_timetable


def reformat_times(timetable, vj, base_time):
    '''Turns the time deltas into time of day, final column is formatted as string'''

    timetable[f"{vj.VehicleJourneyCode}"] = timetable[f"{vj.VehicleJourneyCode}"].cumsum()
    timetable[f"{vj.VehicleJourneyCode}"] = timetable[f"{vj.VehicleJourneyCode}"].map(lambda x: x + base_time)
    timetable[f"{vj.VehicleJourneyCode}"] = timetable[f"{vj.VehicleJourneyCode}"].map(lambda x: x.strftime('%H:%M'))

    return timetable[f"{vj.VehicleJourneyCode}"]

def add_dataframe_headers(direction, operating_days, JourneyPattern_id, RouteRef, lineref):
    """Populate headers with information associated to each individual VJ"""

    direction.loc[-1] = ["Operating Days ", "->", "->", "->", "->", operating_days]
    direction.loc[-2] = ["Journey Pattern ", "->", "->", "->", "->", JourneyPattern_id]
    direction.loc[-3] = ["RouteID", "->", "->", "->", "->", RouteRef]
    direction.loc[-4] = ["Line", "->", "->", "->", "->", lineref]
    direction.index = direction.index + 1  # shifting index
    direction.sort_index(inplace=True)

    return direction

def create_dataclasses():
    """Using the xml file, dataclasses are created for each element"""

    with open(r'timetables/57.xml', 'r', encoding='utf-8') as file:
        xml_text = file.read()
        xml_json = xmltodict.parse(xml_text, process_namespaces=False, attr_prefix='_')
        xml_root = xml_json['TransXChange']
        services_json = xml_root['Services']['Service']
        stops_json = xml_root["StopPoints"]
        vehicle_journey_json = xml_root['VehicleJourneys']
        journey_pattern_json = xml_root['JourneyPatternSections']

        if isinstance(services_json['Lines']['Line'], dict):
            services_json['Lines']['Line'] = [services_json['Lines']['Line']]

        if isinstance(journey_pattern_json['JourneyPatternSection'], dict):
            journey_pattern_json['JourneyPatternSection'] = [journey_pattern_json['JourneyPatternSection']]

        if isinstance(services_json['StandardService']['JourneyPattern'], dict):
            services_json['StandardService']['JourneyPattern'] = [services_json['StandardService']['JourneyPattern']]

        if isinstance(vehicle_journey_json['VehicleJourney'], dict):
            vehicle_journey_json['VehicleJourney'] = [vehicle_journey_json['VehicleJourney']]

        #Dictionaries converted to dataclasses
        service_object = from_dict(data_class=Service, data=services_json)
        stop_object = from_dict(data_class=StopPoints, data=stops_json)
        vehicle_journey = from_dict(data_class=VehicleJourneys, data=vehicle_journey_json)
        journey_pattern_section_object = from_dict(data_class=JourneyPatternSections, data=journey_pattern_json)

        return service_object, stop_object, vehicle_journey, journey_pattern_section_object


def map_indicies(service_object,stop_object, vehicle_journey,journey_pattern_section_object):
    """Initialise values to be used when generating timetables"""

    # List of journey patterns in service object
    journey_pattern_list = service_object.StandardService.JourneyPattern

    # Iterate once through JPs and JPS to find the indices in the list of each id
    journey_pattern_index = {key.id: value for value, key in enumerate(service_object.StandardService.JourneyPattern)}
    journey_pattern_section_index = {key.id: value for value, key in enumerate(journey_pattern_section_object.JourneyPatternSection)}

    # Map stop point refs
    stop_point_index = {key.StopPointRef: value for value, key in enumerate(stop_object.AnnotatedStopPointRef)}

    return journey_pattern_section_index, journey_pattern_index, journey_pattern_list, stop_point_index


def organise_timetables(service_object,collated_timetable_outbound, collated_timetable_inbound):
    """Ordering the timetables correctly"""

    service_code = str(service_object.ServiceCode)

    if not collated_timetable_outbound.empty:

        # ensuring the vjs times are sorted in ascending order
        collated_timetable_outbound.iloc[:, 5:] = collated_timetable_outbound.iloc[:, 5:].iloc[:, ::-1].values

        # ensuring the sequence numbers are sorted in ascending order
        collated_timetable_outbound.iloc[4:] = collated_timetable_outbound.iloc[4:].sort_values(by="Sequence Number",
                                                                                                ascending=True)

        # add this to a collection of outbound timetable dataframes in a dictionary
        outbound_timetables[service_code] = collated_timetable_outbound.to_dict()

    if not collated_timetable_inbound.empty:

        # ensuring the vjs times are sorted in ascending order
        collated_timetable_inbound.iloc[:, 5:] = collated_timetable_inbound.iloc[:, 5:].iloc[:, ::-1].values

        # ensuring the sequence numbers are sorted in ascending order
        collated_timetable_inbound.iloc[4:] = collated_timetable_inbound.iloc[4:].sort_values(by="Sequence Number",
                                                                                              ascending=True)

        # add this to a collection of inbound timetable dataframes in a dictionary
        inbound_timetables[service_code] = collated_timetable_inbound.to_dict()

    return collated_timetable_outbound, collated_timetable_inbound

def generate_timetable():

    """Extracts timetable information for a VJ indvidually and
    adds to a collated dataframe of vjs, split by outbound and inbound"""

    service_object, stop_object, vehicle_journey, journey_pattern_section_object = create_dataclasses()
    journey_pattern_section_index, journey_pattern_index, journey_pattern_list, stop_point_index = map_indicies(service_object,stop_object, vehicle_journey,journey_pattern_section_object)

    # Define a base time to add run times to
    base_time = datetime.datetime(2000, 1, 1, 0, 0, 0)

    #Dataframe to store all inbound vjs together
    collated_timetable_inbound = pd.DataFrame()

    # Dataframe to store all outbound vjs together
    collated_timetable_outbound = pd.DataFrame()

    # Iterate through all vehicle journeys in the file
    for vj in vehicle_journey.VehicleJourney:

        departure_time = pd.Timedelta(vj.DepartureTime)

        vj_columns = ["Sequence Number", "Stop Point Ref", "Latitude", "Longitude", "Common Name", f"{vj.VehicleJourneyCode}"]

        # init empty timetable for outbound Vehicle journey
        outbound = pd.DataFrame(columns=vj_columns)

        # init empty timetable for inbound Vehicle journey
        inbound = pd.DataFrame(columns=vj_columns)

        if vj.LineRef[-1] == ":":
            lineref = vj.LineRef.split(':')[-2]
        else:
            lineref = vj.LineRef.split(':')[-1]

        vjtl_index = {}

        if vj.VehicleJourneyTimingLink is not None:
            vjtl_index = {key.JourneyPatternTimingLinkRef: value for value, key in enumerate(vj.VehicleJourneyTimingLink)}

        # Create vars for relevant indices of this vehicle journey
        vehicle_journey_jp_index = journey_pattern_index[vj.JourneyPatternRef]

        direction = service_object.StandardService.JourneyPattern[vehicle_journey_jp_index].Direction
        RouteRef = service_object.StandardService.JourneyPattern[vehicle_journey_jp_index].RouteRef
        JourneyPattern_id = service_object.StandardService.JourneyPattern[vehicle_journey_jp_index].id

        # Get the journey pattern sections for this vehicle journey, can be a single string or a list of strings
        vehicle_journey_jps_list = service_object.StandardService.JourneyPattern[journey_pattern_index[vj.JourneyPatternRef]].JourneyPatternSectionRefs

        # If there are multiple JPS, put them into a single list for later
        if isinstance(vehicle_journey_jps_list, list):
            vehicle_journey_jps_index = [journey_pattern_section_index[jpsr] for jpsr in journey_pattern_list[vehicle_journey_jp_index].JourneyPatternSectionRefs]
            all_jptl = [[jptl for jptl in journey_pattern_section_object.JourneyPatternSection[x].JourneyPatternTimingLink] for x in vehicle_journey_jps_index]
            flat_jptl = [jptl for sublist in all_jptl for jptl in sublist]

        # if just one JPS, find the journey pattern section directly for later
        else:
            vehicle_journey_jps_index = journey_pattern_section_index[vehicle_journey_jps_list]
            flat_jptl = journey_pattern_section_object.JourneyPatternSection[vehicle_journey_jps_index].JourneyPatternTimingLink


        # Mark the first JPTL
        first = True

        # Loop through relevant timing links

        for JourneyPatternTimingLink in flat_jptl:

            # first JPTL should use 'From' AND 'To' stop data
            if first:

                # remaining JPTLs are not the first one
                first = False

                timetable_sequence = next_jptl_in_sequence(JourneyPatternTimingLink,
                                                           departure_time,
                                                           vj,
                                                           vjtl_index,
                                                           stop_object,
                                                           stop_point_index,
                                                           first_jptl=True)

                # Add first sequence, stop ref and departure time
                first_timetable_row = pd.DataFrame([timetable_sequence[0]], columns=outbound.columns)

                # Add To sequence number and stop point ref to the initial timetable

                if direction == 'outbound':
                    outbound = pd.concat([outbound, first_timetable_row], ignore_index=True)
                    outbound.loc[len(outbound)] = timetable_sequence[1]

                elif direction == 'inbound':
                    inbound = pd.concat([inbound, first_timetable_row], ignore_index=True)
                    inbound.loc[len(inbound)] = timetable_sequence[1]
                else:
                    print(f'Unknown Direction: {direction}')

            else:
                timetable_sequence = next_jptl_in_sequence(JourneyPatternTimingLink, departure_time,vj, vjtl_index,stop_object, stop_point_index)

                if direction == 'outbound':
                    outbound.loc[len(outbound)] = timetable_sequence
                elif direction == 'inbound':
                    inbound.loc[len(inbound)] = timetable_sequence
                else:
                    print(f'Unknown Direction: {direction}')

        if vj.OperatingProfile is None:
            days = service_object.OperatingProfile.RegularDayType.DaysOfWeek
        else:
            days = vj.OperatingProfile.RegularDayType.DaysOfWeek

        if days is None and (service_object.OperatingProfile.BankHolidayOperation.DaysOfOperation is not None or vj.OperatingProfile.BankHolidayOperation.DaysOfOperation is not None):
            operating_days="Holidays Only"
        else:
            operating_days = extract_timetable_operating_days(days)

        if not outbound.empty:
            outbound[f"{vj.VehicleJourneyCode}"] = reformat_times(outbound, vj, base_time)
            outbound = add_dataframe_headers(outbound, operating_days, JourneyPattern_id, RouteRef, lineref)

        if not inbound.empty:
            inbound[f"{vj.VehicleJourneyCode}"] = reformat_times(inbound, vj, base_time)
            inbound = add_dataframe_headers(inbound, operating_days, JourneyPattern_id, RouteRef, lineref)

        # collect vj information together for outbound
        collated_timetable_outbound = collate_vjs(outbound, collated_timetable_outbound)

        # collect vj information together for inbound
        collated_timetable_inbound = collate_vjs(inbound, collated_timetable_inbound)

    collated_timetable_outbound, collated_timetable_inbound = organise_timetables(service_object,collated_timetable_outbound, collated_timetable_inbound)



    return collated_timetable_outbound, collated_timetable_inbound


outbound_timetables = {}
inbound_timetables = {}


generate_timetable()

#service_object,stop_object, vehicle_journey,journey_pattern_section_object=create_dataclasses()
#collated_timetable_outbound, collated_timetable_inbound = generate_timetable(service_object,stop_object, vehicle_journey,journey_pattern_section_object)
