#!/usr/bin/env python
# -*- coding: utf-8 -*-

""":Mod: metapype_client.py

:Synopsis:

:Author:
    costa

:Created:
    7/27/18
"""
import collections
import daiquiri
import json
import os.path

from metapype.eml2_1_1 import export, validate, names, rule
from metapype.model.node import Node, Shift
from metapype.model import io


logger = daiquiri.getLogger('metapyp_client: ' + __name__)

def list_responsible_parties(eml_node:Node=None, node_name:str=None):
    rp_list = []
    if eml_node:
        dataset_node = eml_node.find_child(names.DATASET)
        if dataset_node:
            rp_nodes = dataset_node.find_all_children(node_name)
            RP_Entry = collections.namedtuple(
                'RP_Entry', ["id", "label", "edit_value", "remove_value"], 
                verbose=False, rename=False)
            for rp_node in rp_nodes:
                label = compose_rp_label(rp_node)
                id = rp_node.id
                rp_entry = RP_Entry(
                    id=id, label=label, edit_value='Edit', 
                    remove_value='Remove')
                rp_list.append(rp_entry)
    return rp_list


def list_geographic_coverages(eml_node:Node=None):
    gc_list = []
    if eml_node:
        dataset_node = eml_node.find_child(names.DATASET)
        if dataset_node:
            coverage_node = eml_node.find_child(names.COVERAGE)
            if coverage_node:
                gc_nodes = coverage_node.find_all_children(names.GEOGRAPHICCOVERAGE)
                GC_Entry = collections.namedtuple(
                    'GC_Entry', ["id", "geographic_description", "label"], 
                    verbose=False, rename=False)
                for gc_node in gc_nodes:
                    geographic_description_node = \
                        gc_node.find_child(names.GEOGRAPHICDESCRIPTION)
                    geographic_description = geographic_description_node.content
                    label = compose_gc_label(gc_node)
                    id = gc_node.id
                    gc_entry = GC_Entry(id=id, geographic_description=geographic_description, label=label)
                    gc_list.append(gc_entry)
    return gc_list


def compose_gc_label(gc_node:Node=None):
    '''
    Composes a label for a geographic coverage table entry
    '''
    label = ''
    if gc_node:
        bc_node = gc_node.find_child(names.BOUNDINGCOORDINATES)
        if bc_node:
            wbc_node = bc_node.find_child(names.WESTBOUNDINGCOORDINATE)
            ebc_node = bc_node.find_child(names.EASTBOUNDINGCOORDINATE)
            nbc_node = bc_node.find_child(names.NORTHBOUNDINGCOORDINATE)
            sbc_node = bc_node.find_child(names.SOUTHBOUNDINGCOORDINATE)
            if wbc_node and ebc_node and nbc_node and sbc_node:
                coordinate_list = [str(wbc_node.content),
                                   str(ebc_node.content),
                                   str(nbc_node.content),
                                   str(sbc_node.content)]
                label = ', '.join(coordinate_list)
    return label


def list_temporal_coverages(eml_node:Node=None):
    tc_list = []
    if eml_node:
        dataset_node = eml_node.find_child(names.DATASET)
        if dataset_node:
            coverage_node = eml_node.find_child(names.COVERAGE)
            if coverage_node:
                tc_nodes = coverage_node.find_all_children(names.TEMPORALCOVERAGE)
                TC_Entry = collections.namedtuple(
                    'TC_Entry', ["id", "begin_date", "end_date"],
                    verbose=False, rename=False)
                for tc_node in tc_nodes:
                    id = tc_node.id

                    single_datetime_nodes = tc_node.find_all_children(names.SINGLEDATETIME)
                    if single_datetime_nodes:
                        for sd_node in single_datetime_nodes:
                            calendar_date_node = sd_node.find_child(names.CALENDARDATE)
                            if calendar_date_node:
                                begin_date = calendar_date_node.content
                                end_date = ''
                                tc_entry = TC_Entry(id=id, begin_date=begin_date, end_date=end_date)
                                tc_list.append(tc_entry)

                    range_of_dates_nodes = tc_node.find_all_children(names.RANGEOFDATES)
                    if range_of_dates_nodes:
                        for rod_node in range_of_dates_nodes:
                            begin_date_node = rod_node.find_child(names.BEGINDATE)
                            if begin_date_node:
                                calendar_date_node = begin_date_node.find_child(names.CALENDARDATE)
                                begin_date = calendar_date_node.content
                            end_date_node = rod_node.find_child(names.ENDDATE)
                            if end_date_node:
                                calendar_date_node = end_date_node.find_child(names.CALENDARDATE)
                                end_date = calendar_date_node.content
                            tc_entry = TC_Entry(id=id, begin_date=begin_date, end_date=end_date)
                            tc_list.append(tc_entry)
    return tc_list


def add_child(parent_node:Node, child_node:Node):
    if parent_node and child_node:
        parent_rule = rule.get_rule(parent_node.name)
        index = parent_rule.child_insert_index(parent_node, child_node)
        parent_node.add_child(child_node, index=index)


def move_up(parent_node:Node, child_node:Node):
    if parent_node and child_node:
        parent_node.shift(child_node, Shift.LEFT)


def move_down(parent_node:Node, child_node:Node):
    if parent_node and child_node:
        parent_node.shift(child_node, Shift.RIGHT)


def compose_rp_label(rp_node:Node=None):
    label = ''
    if rp_node:
        individual_name_node = rp_node.find_child(names.INDIVIDUALNAME)
        individual_name_label = (
            compose_individual_name_label(individual_name_node))
        organization_name_label = (
            compose_simple_label(rp_node, names.ORGANIZATIONNAME))
        position_name_label = (
            compose_simple_label(rp_node, names.POSITIONNAME))
        
        if individual_name_label:
            label = individual_name_label
        if position_name_label:
            label = label + ', ' + position_name_label
        if organization_name_label:
            label = label + ', ' + organization_name_label
    return label


def compose_individual_name_label(rp_node:Node=None):
    label = ''
    if rp_node:
        salutation_nodes = rp_node.find_all_children(names.SALUTATION)
        if salutation_nodes:
            for salutation_node in salutation_nodes:
                if salutation_node and salutation_node.content:
                    label = label + " " + salutation_node.content
        
        given_name_nodes = rp_node.find_all_children(names.GIVENNAME)
        if given_name_nodes:
            for given_name_node in given_name_nodes:
                if given_name_node and given_name_node.content:
                    label = label + " " + given_name_node.content
        
        surname_node = rp_node.find_child(names.SURNAME)
        if surname_node and surname_node.content:
            label = label + " " + surname_node.content

    return label


def compose_simple_label(rp_node:Node=None, child_node_name:str=''):
    label = ''
    if rp_node and child_node_name:
        child_node = rp_node.find_child(child_node_name)
        if child_node and child_node.content:
            label = child_node.content
    return label


def load_eml(packageid:str=None):
    eml_node = None
    filename = f"{packageid}.json"
    if os.path.isfile(filename):
        with open(filename, "r") as json_file:
            json_obj = json.load(json_file)
            eml_node = io.from_json(json_obj)
    return eml_node


def remove_child(node_id:str=None):
    if node_id:
        child_node = Node.get_node_instance(node_id)
        if child_node:
            parent_node = child_node.parent
            if parent_node:
                parent_node.remove_child(child_node)


def store_eml(packageid:str=None, eml_node:Node=None):
    if packageid and eml_node:
        pass
        #session[packageid] = eml_node


def retrieve_eml(packageid:str=None):
    eml_node = None
    if packageid:
        pass
        #eml_node = session[packageid]
    return eml_node


def log_as_xml(node: Node):
    xml_str = export.to_xml(node)
    logger.info("\n\n" + xml_str)


def save_both_formats(packageid:str=None, eml_node:Node=None):
    save_eml(packageid=packageid, eml_node=eml_node, format='json')
    save_eml(packageid=packageid, eml_node=eml_node, format='xml')


def save_eml(packageid:str=None, eml_node:Node=None, format:str='json'):
    if packageid:
        if eml_node is not None:
            metadata_str = None

            if format == 'json':
                metadata_str = io.to_json(eml_node)
            elif format == 'xml':
                xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
                xml_str = export.to_xml(eml_node)
                metadata_str = xml_declaration + xml_str
            
            if metadata_str:
                filename = f"{packageid}.{format}"
                with open(filename, "w") as fh:
                    fh.write(metadata_str)
        else:
            raise Exception(f"No EML node was supplied for saving EML.")
    else:
        raise Exception(f"No packageid value was supplied for saving EML.")


def validate_tree(node:Node):
    msg = ''
    if node:
        try:
            validate.tree(node)
            msg = f"{node.name} node is valid"
        except Exception as e:
            msg = str(e)

    return msg


def create_eml(packageid=None):
    eml_node = load_eml(packageid=packageid)

    if not eml_node:
        eml_node = Node(names.EML)
        eml_node.add_attribute('packageId', packageid)
        eml_node.add_attribute('system', 'https://pasta.edirepository.org')
        dataset_node = Node(names.DATASET, parent=eml_node)
        add_child(eml_node, dataset_node)

        try:
            save_both_formats(packageid=packageid, eml_node=eml_node)
        except Exception as e:
            logger.error(e)


def create_title(title=None, packageid=None):
    eml_node = load_eml(packageid=packageid)

    dataset_node = eml_node.find_child('dataset')
    if dataset_node:
        title_node = dataset_node.find_child('title')
        if not title_node:
            title_node = Node(names.TITLE, parent=dataset_node)
            add_child(dataset_node, title_node)
    else:
        dataset_node = Node(names.DATASET, parent=eml_node)
        add_child(eml_node, dataset_node)
        title_node = Node(names.TITLE, parent=dataset_node)
        add_child(dataset_node, title_node)

    title_node.content = title

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def create_pubdate(pubdate=None, packageid=None):
    eml_node = load_eml(packageid=packageid)

    dataset_node = eml_node.find_child(names.DATASET)
    if dataset_node:
        pubdate_node = dataset_node.find_child(names.PUBDATE)
        if not pubdate_node:
            pubdate_node = Node(names.PUBDATE, parent=dataset_node)
            add_child(dataset_node, pubdate_node)
    else:
        dataset_node = Node(names.DATASET, parent=eml_node)
        add_child(eml_node, dataset_node)
        pubdate_node = Node(names.PUBDATE, parent=dataset_node)
        add_child(dataset_node, pubdate_node)

    pubdate_node.content = pubdate

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def create_abstract(packageid=None, abstract=None):
    eml_node = load_eml(packageid=packageid)

    dataset_node = eml_node.find_child(names.DATASET)
    if dataset_node:
        abstract_node = dataset_node.find_child(names.ABSTRACT)
        if not abstract_node:
            abstract_node = Node(names.ABSTRACT, parent=dataset_node)
            add_child(dataset_node, abstract_node)
    else:
        dataset_node = Node(names.DATASET, parent=eml_node)
        add_child(eml_node, dataset_node)
        abstract_node = Node(names.ABSTRACT, parent=dataset_node)
        add_child(dataset_node, abstract_node)

    abstract_node.content = abstract

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def add_keyword(packageid:str=None, keyword:str=None, keyword_type:str=None):
    if keyword:
        eml_node = load_eml(packageid=packageid)

        dataset_node = eml_node.find_child(names.DATASET)
        if not dataset_node:
            dataset_node = Node(names.DATASET, parent=eml_node)
            add_child(eml_node, dataset_node)

        keywordset_node = dataset_node.find_child(names.KEYWORDSET)
        if not keywordset_node:
            keywordset_node = Node(names.KEYWORDSET, parent=dataset_node)
            add_child(dataset_node, keywordset_node)

        keyword_node = None
        
        # Does a matching keyword node already exist?
        keyword_nodes = keywordset_node.find_all_children(names.KEYWORD)
        for child_node in keyword_nodes:
            if child_node.content == keyword:
                keyword_node = child_node
                break
        
        if not keyword_node:
            keyword_node = Node(names.KEYWORD, parent=keywordset_node)
            keyword_node.content = keyword
            add_child(keywordset_node, keyword_node)
        
        if keyword_type:
            keyword_node.add_attribute(name='keywordType', value=keyword_type)

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def remove_keyword(packageid:str=None, keyword:str=None):
    if keyword:
        eml_node = load_eml(packageid=packageid)
        keywordset_node = eml_node.find_child(names.KEYWORDSET)
        if keywordset_node:
            current_keywords = \
                keywordset_node.find_all_children(child_name=names.KEYWORD)
            for keyword_node in current_keywords:
                if keyword_node.content == keyword:
                    keywordset_node.remove_child(keyword_node)

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def create_keywords(packageid:str=None, keywords_list:list=[]):
    eml_node = load_eml(packageid=packageid)

    dataset_node = eml_node.find_child(names.DATASET)
    if dataset_node:
        keywordset_node = dataset_node.find_child(names.KEYWORDSET)
        if keywordset_node:
            # Get rid of the old keyword set if it exists
            dataset_node.remove_child(keywordset_node)
    else:
        dataset_node = Node(names.DATASET, parent=eml_node)
        add_child(eml_node, dataset_node)
    
    if keywords_list:
        keywordset_node = Node(names.KEYWORDSET, parent=dataset_node)
        add_child(dataset_node, keywordset_node)
        for keyword in keywords_list:
            keyword_node = Node(names.KEYWORD, parent=keywordset_node)
            keyword_node.content = keyword
            add_child(keywordset_node, keyword_node)

    try:
        save_both_formats(packageid=packageid, eml_node=eml_node)
    except Exception as e:
        logger.error(e)


def create_geographic_coverage(
                   geographic_coverage_node:Node=None,
                   geographic_description:str=None,
                   wbc:str=None,
                   ebc:str=None,
                   nbc:str=None,
                   sbc:str=None):
    try:
        geographic_description_node = Node(names.GEOGRAPHICDESCRIPTION)
        geographic_description_node.content = geographic_description
        add_child(geographic_coverage_node, geographic_description_node)

        bounding_coordinates_node = Node(names.BOUNDINGCOORDINATES)

        wbc_node = Node(names.WESTBOUNDINGCOORDINATE)
        wbc_node.content = wbc
        add_child(bounding_coordinates_node, wbc_node)

        ebc_node = Node(names.EASTBOUNDINGCOORDINATE)
        ebc_node.content = ebc
        add_child(bounding_coordinates_node, ebc_node)

        nbc_node = Node(names.NORTHBOUNDINGCOORDINATE)
        nbc_node.content = nbc
        add_child(bounding_coordinates_node, nbc_node)

        sbc_node = Node(names.SOUTHBOUNDINGCOORDINATE)
        sbc_node.content = sbc
        add_child(bounding_coordinates_node, sbc_node)

        add_child(geographic_coverage_node, bounding_coordinates_node)

        return geographic_coverage_node

    except Exception as e:
        logger.error(e)


def create_temporal_coverage(
                   temporal_coverage_node:Node=None,
                   begin_date:str=None,
                   end_date:str=None):
    try:
        if begin_date and end_date:
            range_of_dates_node = Node(names.RANGEOFDATES, parent=temporal_coverage_node)
            add_child(temporal_coverage_node, range_of_dates_node)

            begin_date_node = Node(names.BEGINDATE, parent=range_of_dates_node)
            add_child(range_of_dates_node, begin_date_node)
            begin_calendar_date_node = Node(names.CALENDARDATE, parent=begin_date_node)
            add_child(begin_date_node, begin_calendar_date_node)
            begin_calendar_date_node.content = begin_date

            end_date_node = Node(names.ENDDATE, parent=range_of_dates_node)
            add_child(range_of_dates_node, end_date_node)
            end_calendar_date_node = Node(names.CALENDARDATE, parent=end_date_node)
            add_child(end_date_node, end_calendar_date_node)
            end_calendar_date_node.content = end_date
        elif begin_date:
            single_datetime_node = Node(names.SINGLEDATETIME, parent=temporal_coverage_node)
            add_child(temporal_coverage_node, single_datetime_node)
            calendar_date_node = Node(names.CALENDARDATE, parent=single_datetime_node)
            add_child(single_datetime_node, calendar_date_node)
            calendar_date_node.content = begin_date

        return temporal_coverage_node

    except Exception as e:
        logger.error(e)


def create_responsible_party(
                   parent_node:Node=None,
                   responsible_party_node:Node=None,
                   packageid:str=None, 
                   salutation:str=None,
                   gn:str=None,
                   sn:str=None,
                   organization:str=None,
                   position_name:str=None,
                   address_1:str=None,
                   address_2:str=None,
                   city:str=None,
                   state:str=None,
                   postal_code:str=None,
                   country:str=None,
                   phone:str=None,
                   fax:str=None,
                   email:str=None,
                   online_url:str=None):
    try:
        node_name = responsible_party_node.name

        if parent_node:
            old_responsible_party_node = parent_node.find_child(node_name)
            if old_responsible_party_node:
                pass
                # Get rid of the old node if it exists
                #dataset_node.remove_child(old_responsible_party_node)

        if salutation or gn or sn:
            individual_name_node = Node(names.INDIVIDUALNAME)
            if salutation:
                salutation_node = Node(names.SALUTATION)
                salutation_node.content = salutation
                add_child(individual_name_node, salutation_node)
            if gn:
                given_name_node = Node(names.GIVENNAME)
                given_name_node.content = gn
                add_child(individual_name_node, given_name_node)
            if sn:
                surname_node = Node(names.SURNAME)
                surname_node.content = sn
                add_child(individual_name_node, surname_node)
            add_child(responsible_party_node, individual_name_node)

        if organization:
            organization_name_node = Node(names.ORGANIZATIONNAME)
            organization_name_node.content = organization
            add_child(responsible_party_node, organization_name_node)

        if position_name:
            position_name_node = Node(names.POSITIONNAME)
            position_name_node.content = position_name
            add_child(responsible_party_node, position_name_node)

        if address_1 or address_2 or city or state or postal_code or country:
            address_node = Node(names.ADDRESS)

            if address_1:
                delivery_point_node_1 = Node(names.DELIVERYPOINT)
                delivery_point_node_1.content = address_1
                add_child(address_node, delivery_point_node_1)

            if address_2:
                delivery_point_node_2 = Node(names.DELIVERYPOINT)
                delivery_point_node_2.content = address_2
                add_child(address_node, delivery_point_node_2)

            if city:
                city_node = Node(names.CITY)
                city_node.content = city
                add_child(address_node, city_node)

            if state:
                administrative_area_node = Node(names.ADMINISTRATIVEAREA)
                administrative_area_node.content = state
                add_child(address_node, administrative_area_node)

            if postal_code:
                postal_code_node = Node(names.POSTALCODE)
                postal_code_node.content = postal_code
                add_child(address_node, postal_code_node)

            if country:
                country_node = Node(names.COUNTRY)
                country_node.content = country
                add_child(address_node,country_node)

            add_child(responsible_party_node, address_node)

        if phone:
            phone_node = Node(names.PHONE)
            phone_node.content = phone
            phone_node.add_attribute('phonetype', 'voice')
            add_child(responsible_party_node, phone_node)

        if fax:
            fax_node = Node(names.PHONE)
            fax_node.content = fax
            fax_node.add_attribute('phonetype', 'facsimile')
            add_child(responsible_party_node, fax_node)

        if email:
            email_node = Node(names.ELECTRONICMAILADDRESS)
            email_node.content = email
            add_child(responsible_party_node, email_node)

        if online_url:
            online_url_node = Node(names.ONLINEURL)
            online_url_node.content = online_url
            add_child(responsible_party_node, online_url_node)
             
        return responsible_party_node

    except Exception as e:
        logger.error(e)


def validate_minimal(packageid=None, title=None, contact_gn=None, 
                     contact_sn=None, creator_gn=None, creator_sn=None):
    msg = ''
    eml = Node(names.EML)

    eml.add_attribute('packageId', packageid)
    eml.add_attribute('system', 'https://pasta.edirepository.org')

    dataset = Node(names.DATASET, parent=eml)
    add_child(eml, dataset)

    title_node = Node(names.TITLE)
    title_node.content = title
    add_child(dataset, title_node)
    
    creator_node = Node(names.CREATOR, parent=dataset)
    add_child(dataset, creator_node)

    individualName_creator = Node(names.INDIVIDUALNAME, parent=creator_node)
    add_child(creator_node, individualName_creator)

    givenName_creator = Node(names.GIVENNAME, parent=individualName_creator)
    givenName_creator.content = creator_gn
    add_child(individualName_creator, givenName_creator)

    surName_creator = Node(names.SURNAME, parent=individualName_creator)
    surName_creator.content = creator_sn
    add_child(individualName_creator, surName_creator)

    contact_node = Node(names.CONTACT, parent=dataset)
    add_child(dataset, contact_node)

    individualName_contact = Node(names.INDIVIDUALNAME, parent=contact_node)
    add_child(contact_node, individualName_contact)

    givenName_contact = Node(names.GIVENNAME, parent=individualName_contact)
    givenName_contact.content = contact_gn
    add_child(individualName_contact, givenName_contact)

    surName_contact = Node(names.SURNAME, parent=individualName_contact)
    surName_contact.content = contact_sn
    add_child(individualName_contact, surName_contact)

    xml_str =  export.to_xml(eml)
    print(xml_str)

    if eml:
        msg = validate_tree(eml)

    return msg
