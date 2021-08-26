# cython: language_level=3
import json
import pathlib
import re

import xmltodict


def save_list(xmllist, filename):
    newstr = '\n'.join(xmllist)
    file1 = pathlib.Path(filename)
    with file1.open('w') as f:
        f.write(newstr)


def get_var(var_str):
    var_list = var_str.lstrip('(').rstrip(')').split(',')
    var_list = [var.strip().strip('\'') for var in var_list]
    key = var_list[0]
    val = var_list[3]
    return key, val


def replace(original_str: str, old: str, new: str, reverse=False):
    if reverse:
        return original_str.replace(new, old, 1)
    else:
        return original_str.replace(old, new, 1)


def replace_operation(matcher):
    key = matcher.group(1)
    if key[0] == '\'' and key[-1] == '\'':
        key = key \
            .replace("'", "__APOSTROPHE__") \
            .replace("+", "__PLUS__") \
            .replace("-", "__MINUS__") \
            .replace('(', '__LEFT_BRACKET__') \
            .replace(')', '__RIGHT_BRACKET__') \
            .replace('/', '__SLASH__')
    if key[0].isdigit():
        key = '__DIGI__' + key
    key = key.replace(' ', '__BLANK__')
    value = matcher.group(2)
    if 'MaterialValue' in key:
        value = value.replace('\"', '').replace('\'', '')
    return key, value


def replace___APOSTROPHE__(matcher):
    newline = matcher.group(1)
    if newline == '':
        newline = '__EMPTY__' + newline
    if newline[0] == '-' and newline[1].isdigit():
        newline = '__NEG__' + newline[1:]
    if newline[0] == '\'' and newline[-1] == '\'':
        newline = newline.replace('\'', '__APOSTROPHE__')
    if newline[0].isdigit():
        newline = '__DIGI__' + newline
    newline = newline \
        .replace('/', '_r_') \
        .replace('.', '_d_') \
        .replace(' ', '__BLANK__') \
        .replace('(', '__LEFT_BRACKET__') \
        .replace(')', '__RIGHT_BRACKET__')
    return newline


def prefix_replace(newline, tabs, prefix='$begin \''):
    begin_newline = tabs + prefix + newline.replace("_r_",
                                                    "/").replace(
        "_d_", ".").replace("__BLANK__", " ") + '\''
    return begin_newline


class AEDT:
    pattern_end = '\\$end \'(.*)\''
    pattern_begin = '\\$begin \'(.*)\''
    pattern_value = r'^(.[^=]*)=(.*)$'
    pattern_function = r'^(\w+)(\(.*\))$'
    pattern_array = r"^(\S+)\[([\w\W]+)\]$"

    var_pattern_format = r"('{}','UD','','{}')"

    xml_pattern_end = r"</(.[^=]*)>"
    xml_pattern_begin = r"<([^/].[^=]*)>"
    xml_pattern_short_empty_elements = r"<([^/].[^=]*)/>"

    # value type: "<" + key + " type=\"value\" value=\"" + value + "\"/>";
    xml_pattern_value = r"<(.+) type=\"value\" value=\"(.*)\"\s*/>"

    # function type "<" + newline + " type=\"function\" value=\"" + newline2 + "\"/>"
    xml_pattern_function = r"<(\w+) type=\"function\" value=\"(.*)\"\s*/>"

    # array type  "<" + key + " type=\"array\" value=\"" + value + "\"/>";
    xml_pattern_array = r"<(\w+) type=\"array\" value=\"(.*)\"\s*/>"

    design_names = []
    variables = {}
    reports = {}

    model_types = ['Maxwell2DModel',
                   'Maxwell3DModel',
                   'RMxprtDesign']
    instance_types = ['Maxwell2DDesignInstance',
                      'Maxwell3DDesignInstance',
                      'MaxwellDesignInstance',
                      'RMxprtDesignInstance']

    def __init__(self, aedt_file=None):
        self.aedtProject = {}
        self.levelList = []
        self.setups = {}
        self.parametric_setups = {}
        if aedt_file is not None:
            self.filename = pathlib.Path(aedt_file)
            self.aedtList = self.load_aedt(self.filename)

        # self.xml_tree=self.read_xml()

    def parse_aedt(self):
        designs = []
        for model_type in self.model_types:
            if model_type in self.aedtProject['AnsoftProject'].keys():

                if type(self.aedtProject['AnsoftProject'][
                            model_type]) is list:
                    designs += self.aedtProject['AnsoftProject'][model_type]
                else:
                    designs.append(
                        self.aedtProject['AnsoftProject'][model_type])
        temp_instance = self.aedtProject['AnsoftProject'] \
            ['DataInstances']['Instance']
        if type(temp_instance) is list:
            report_instances = temp_instance
        else:
            report_instances = [temp_instance]
        for design in designs:
            temp_var = []
            design_name = design['Name']['@value']
            self.design_names.append(design_name)
            self.variables[design_name] = {}
            if 'ModelSetup' in list(design.keys()):
                if 'Properties' in design['ModelSetup'].keys():
                    if 'VariableProp' in design['ModelSetup'] \
                            ['Properties'].keys():
                        temp_var = design['ModelSetup'] \
                            ['Properties'] \
                            ['VariableProp']
            elif 'MachineSetup' in design.keys():
                if 'Properties' in design['MachineSetup'].keys():
                    if 'VariableProp' in design['MachineSetup'] \
                            ['Properties'].keys():
                        temp_var = design['MachineSetup'] \
                            ['Properties'] \
                            ['VariableProp']
            else:
                pass
            if not isinstance(temp_var, list):
                temp_var = [temp_var]
            for var1 in temp_var:
                key, value = get_var(var1['@value'])
                self.variables[design_name][key] = value

            exclude_dict_key = ['NextUniqueID', 'MoveBackwards']
            # parse setups
            setup_tree = design['AnalysisSetup']['SolveSetups']
            self.setups[design_name] = {}
            for key, val in setup_tree.items():
                if key not in exclude_dict_key:
                    self.setups[design_name][key] = val
            # parse parametric setups
            self.parametric_setups[design_name] = {}
            parametric_tree = design['Optimetrics']['OptimetricsSetups']
            for key, val in parametric_tree.items():
                if key not in exclude_dict_key:
                    self.parametric_setups[design_name][key] = val
        for report_instance in report_instances:
            for design_name in self.design_names:
                if design_name in report_instance['DesignEditor']['@value']:
                    for instance_type in self.instance_types:
                        if instance_type in report_instance.keys():
                            self.reports[design_name] = \
                                report_instance[instance_type]['ReportSetup'][
                                    'Reports']

    def save_json(self, filename):
        json_path = pathlib.Path(filename)
        with json_path.open('w') as fp:
            fp.write(json.dumps(self.aedtProject))

    def load_aedt(self, aedt_file):
        self.aedtProject = {}
        self.levelList = []
        self.design_names = []
        self.variables = {}
        self.reports = {}
        if aedt_file is None:
            raise IOError('ANSYS Electronic Desktop Model File not found')
        else:
            p = pathlib.Path(aedt_file)
        with p.open(encoding='utf8', errors='replace') as f:
            self.aedtList = f.readlines()
        fixed_line = ''
        tmp_aedt_list = []
        for line in self.aedtList:
            fixed_line += line
            suffix = line[-2:]
            if suffix == '\\\n':
                # print(line)
                continue
            tmp_aedt_list.append(fixed_line)
            fixed_line = ''
        self.aedtList = tmp_aedt_list
        if len(self.aedtList) == 0:
            raise IOError('ANSYS Electronic Desktop Model File not found')
        self.aedtProject = self.to_dict(self.aedtList)
        self.parse_aedt()

    def to_aedt(self):
        xmlList = xmltodict.unparse(self.aedtProject,
                                    short_empty_elements=True,
                                    pretty=True).split('\n')
        if len(xmlList) < 1:
            raise IndexError('Length of XML > 1')

        aedt_out = []
        for line in xmlList:
            tabs = ''
            line = line.replace('\t', '')
            matcher = re.match(self.xml_pattern_begin, line)
            if matcher:
                short_empty_matcher = re.match(
                    self.xml_pattern_short_empty_elements, line)
                if short_empty_matcher:
                    newline = short_empty_matcher.group(1)
                    newline = newline.replace('__EMPTY__', '')
                    newline = newline.replace("__APOSTROPHE__", "\'")
                    newline = newline.replace('__NEG__', '-')
                    if newline.startswith('__DIGI__'):
                        newline = newline.lstrip('__DIGI__')
                    begin_newline = prefix_replace(newline, tabs)
                    end_newline = prefix_replace(newline, tabs,
                                                 prefix='$end \'')
                    aedt_out.append(begin_newline)
                    aedt_out.append(end_newline)
                else:
                    newline = matcher.group(1)
                    newline = newline.replace("__APOSTROPHE__", "\'") \
                        .replace('__NEG__', '-') \
                        .replace('__LEFT_BRACKET__', '(') \
                        .replace('__RIGHT_BRACKET__', ')')
                    if newline.startswith('__DIGI__'):
                        newline = newline.lstrip('__DIGI__')
                    newline = newline.replace('__EMPTY__', '')
                    newline = prefix_replace(newline, tabs)
                    aedt_out.append(newline)
                    continue

            matcher = re.match(self.xml_pattern_end, line)
            if matcher:
                newline = matcher.group(1)
                newline = newline.replace("__APOSTROPHE__", "\'")
                if newline.startswith('__DIGI__'):
                    newline = newline.lstrip('__DIGI__')
                newline = tabs + '$end \'' + newline \
                    .replace("_r_", "/") \
                    .replace("_d_", ".") \
                    .replace("__BLANK__", " ") + '\''
                aedt_out.append(newline)
                continue

            matcher = re.match(self.xml_pattern_function, line)
            if matcher:
                newline = matcher.group(1).replace("__BLANK__", " ") \
                    .replace("&amp;", "&")
                if newline.startswith('__DIGI__'):
                    newline = newline.lstrip('__DIGI__')
                newline2 = matcher.group(2).replace("&amp;", "&")
                newline = tabs + newline + newline2
                aedt_out.append(newline)
                continue

            matcher = re.match(self.xml_pattern_value, line)
            if matcher:
                key = matcher.group(1) \
                    .replace('__BLANK__', ' ') \
                    .replace("__APOSTROPHE__", "'") \
                    .replace('__LEFT_BRACKET__', '(') \
                    .replace('__RIGHT_BRACKET__', ')') \
                    .replace('__SLASH__', '/', ) \
                    .replace("__PLUS__", "+") \
                    .replace("__MINUS__", "-")
                if key[0] == '__DIGI__':
                    key = key[1:]

                value = matcher.group(2)
                if 'MaterialValue' in key:
                    if value == '':
                        value = '\'\"\"\''
                    else:
                        value = '\'\"' + value + '\"\''

                    # elif ('true' in value) or
                    # ('false' in value) or (value.isdigit()):
                    #     value='\'\"'+value+'\"\''

                aedt_out.append(tabs + key + '=' + '' + value + '')
                continue

            matcher = re.match(self.xml_pattern_array, line)
            if matcher:
                key = matcher.group(1)
                if key[0] == '__DIGI__':
                    key = key[1:]

                value = matcher.group(2)

                aedt_out.append(tabs + key + '[' + value + ']')

        return aedt_out

    def to_xml(self, aedt_list):
        xmlOutput = []
        for line in aedt_list:
            level = line.count('\t')
            self.levelList.append(level)
            line = line.strip()
            matcher = re.match(self.pattern_begin, line)
            if matcher is not None:
                newline = replace___APOSTROPHE__(matcher)
                xmlOutput.append('<' + newline + '>')
                continue

            matcher = re.match(self.pattern_end, line)
            if matcher is not None:
                newline = replace___APOSTROPHE__(matcher)
                xmlOutput.append('</' + newline + '>')
                if newline == "AnsoftProject":
                    break
                continue

            # matcher = re.search(regex, test_str, re.DOTALL)
            matcher = re.search(self.pattern_function, line, re.DOTALL)
            if matcher is not None:
                newline = matcher.group(1).replace(' ', '__BLANK__').replace(
                    '&',
                    '&amp;')
                if newline[0].isdigit():
                    newline = '__DIGI__' + newline
                newline2 = matcher.group(2).replace('&', '&amp;')
                xmlOutput.append(
                    "<" + newline + " type=\"function\" value=\"" + newline2 + "\"/>")
                continue

            matcher = re.match(self.pattern_value, line)
            if matcher is not None:
                key, value = replace_operation(matcher)
                xmlOutput.append(
                    "<" + key + " type=\"value\" value=\"" + value + "\"/>")
                continue
            # 这里顺序是有讲究的
            matcher = re.match(self.pattern_array, line)
            # matcher = re.search(regex, test_str, re.DOTALL)
            if matcher is not None:
                key, value = replace_operation(matcher)
                xmlOutput.append(
                    "<" + key + " type=\"array\" value=\"" + value + "\"/>")
        save_list(xmlOutput, 'out.xml')
        return xmlOutput

    def to_dict(self, aedt_list):
        xmlList = self.to_xml(aedt_list)

        xmlList = ''.join(xmlList)
        return xmltodict.parse(xmlList)

    def save_file(self, filename):
        pathFile = pathlib.Path(filename)
        self.aedtList = self.to_aedt()
        if pathFile.suffix == '.aedt':
            pathFile.write_text('\n'.join(self.aedtList))
        else:
            raise IOError(
                'Error File Extension, use \".aedt\" please.')

    def get_design_names(self):
        return self.design_names

    def get_variables(self):
        return self.variables

    def get_reports(self):
        if self.reports is not None:
            return self.reports
        else:
            return None

    def get_setups(self):
        ret = self.setups
        return ret

    def get_parametric_setups(self):
        ret = self.parametric_setups
        return ret

    def get_design_setup(self, design_name):
        setups = self.get_setups()
        return setups[design_name]

    def get_design_parametric_setup(self, design_name):
        setups = self.get_parametric_setups()
        return setups[design_name]

    def get_design_reports(self, design_name):
        if self.reports is not None:
            return self.reports[design_name]
        else:
            return None

    def get_design_variables(self, design_name):
        return self.variables[design_name]

    def form_var_str(self, key, value):
        return self.var_pattern_format.format(key, value)

    def update_aedt_project(self):
        designs = []
        for model_type in self.model_types:
            if model_type in self.aedtProject['AnsoftProject'].keys():

                if type(self.aedtProject['AnsoftProject'][
                            model_type]) is list:
                    designs += self.aedtProject['AnsoftProject'][model_type]
                else:
                    designs.append(
                        self.aedtProject['AnsoftProject'][model_type])
        for design in designs:
            temp_var = design['ModelSetup']['Properties']['VariableProp']
            for var1 in temp_var:
                key, value = get_var(var1['@value'])
                new_value = self.variables[design['Name']['@value']][key]
                var1['@value'] = self.form_var_str(key, new_value)

    def change_variables(self, design_name, var_name, value):
        if design_name not in self.variables.keys():
            raise NameError('Design {} not found.'.format(design_name))
        else:
            if var_name not in self.variables[design_name].keys():
                raise NameError('Variable name "{}" not found in Design {}.'
                                .format(var_name, design_name))
            else:
                self.variables[design_name][var_name] = value
                self.update_aedt_project()

    def run_simulation(self, ansys_exe, aedt_model_path, design_name,
                       timeout_in_sec):
        pass  # 这里把timeout转成秒

    def run_script(self):
        pass

    def run_script_and_exit(self):
        pass

    def collect_data(self):
        pass
