import posconstants as pc
import random, math

class SendExecCases():
    """Enumeration of return cases for sending and executing move tables. All
    defined cases are encoded / documented here.
    
    To ensure logical completeness of the interface, there is an order in which
    the failure checks are supposed to be applied by petalcontroller:
        
      1. Required power supplies are on?
      2. Required canbuses are enabled?
      3. We are below the moves per hour limit?
      4. We are above the power supply reset rate limit?
      5. We are below the temperature acceptance limit?
      6. Tables wre sent and confirmed...
          a) ...for all required tables?
          b) ...for all tables?
    
    So for example a return value 'FAILED: power off' (e.g. #1 above) does not
    necessarily mean that one of the later error cases in the list would not also
    apply, had petalcontroller gotten to that check.
    """
    def __init__(self, printfunc=print):
        self.printfunc = printfunc
        self.CLEARED = 'cleared'
        self.NORESPONSE = 'no_response'
        self.UNKNOWN = 'unknown'

        self.valid_power_supplies = {'V1', 'V2', 'PS1', 'PS2'}
        self.valid_canbus_ids = {f'can{i:02}' for i in range(100)} | {f'can{i}' for i in range(10)}
        
        self.send_fail_format = {
            self.CLEARED: dict,  # any pos for which move tables were originally defined, but whose memories are now known to be clear
            self.NORESPONSE: dict,  # failed pos, which didn't respond on CAN bus. collection may overlap with cleared or unknown
            self.UNKNOWN: dict,  # failed pos, which might or might not currently have tables loaded
            }  # subdicts have keys = busid strings like 'can11' etc and values = canid ints
        
        self.rate_fail_format = {
            'current_rate': float,  # foo per hour
            'sec_until_ready': float,  # min time (seconds) we must wait until ready again to execute
            }
        
        self.temp_fail_format = {
            busid: dict for busid in self.valid_canbus_ids  # positioners that exceed limit temperature, separated into dicts by busids, that have keys=canids and vals=temperatures
            }
        self.temp_fail_format['other'] = dict
        
        self.SUCCESS = 'SUCCESS'
        self.PARTIAL_SEND = 'PARTIAL SUCCESS: all required moves'
        self.FAIL_SEND = 'FAILED: sending tables'
        self.FAIL_PWROFF = 'FAILED: power off'
        self.FAIL_BUSOFF = 'FAILED: canbus off'
        self.FAIL_MOVERATE = 'FAILED: move rate limit'
        self.FAIL_RESETRATE = 'FAILED: power supply reset rate limit'
        self.FAIL_TEMPLIMIT = 'FAILED: temperature limit'
        self.FAIL_OTHER = 'FAILED: other'
                
        self.defs = {
            self.SUCCESS:        None,  # all requested move tables sent and executed ok
            self.PARTIAL_SEND:   self.send_fail_format,  # any returned pos are in the failed-but-not-required category
            self.FAIL_SEND:      self.send_fail_format,  # return collections will contain some *required* pos for which tables failed to send
            self.FAIL_PWROFF:    [],  # list includes only the power supplies that are disabled
            self.FAIL_BUSOFF:    [],  # list includes only the can buses that are disabled
            self.FAIL_MOVERATE:  self.rate_fail_format,
            self.FAIL_RESETRATE: self.rate_fail_format,
            self.FAIL_TEMPLIMIT: self.temp_fail_format,
            self.FAIL_OTHER:     None,  # any object is accepted as the data value
            }

        
        self.sim_subcases_cycle = sorted(self.send_fail_format)
        self.sim_subcases_last = {self.PARTIAL_SEND: -1, self.FAIL_SEND: -1}
        self.sim_cases_cycle = self.sim_cases_sequence()
        self.sim_cases_last = -1

    def validate(self, pc_response):
        '''Validates output from send_and_execute_tables() provided by petalcontroller.
        Throws an assertion if invalid, otherwise silent.
        '''
        def assert2(test, detail=''):
            msg = f'petalcontroller return data not understood:\n{pc_response}\n{detail}'
            if not test:
                self.printfunc(f'AssertionError: {msg}')  # redundant because of oddities with logging in ICS
            assert test, msg
        
        def validate_numeric(data, key_type=object):
            '''Validates input dict data, ensuring that all values are numeric. Keys
            are also checked to make sure they conform to the argued type.'''
            for k, v in data.items():
                assert2(isinstance(k, key_type), f'expected {key_type}, not {k}')
                assert2(pc.is_number(v), f'expected a number, not {v}')
            
        require_all_expected_keys = {self.FAIL_MOVERATE, self.FAIL_RESETRATE, self.PARTIAL_SEND, self.FAIL_SEND}
        assert2(len(pc_response) == 2, f'bad length {len(pc_response)} for pc_response')
        assert2(isinstance(pc_response, (tuple, list)), 'not a tuple or list')
        errstr = pc_response[0]
        data = pc_response[1]
        assert2(errstr in self.defs, f'undefined errstr {errstr}')
        if errstr == self.FAIL_OTHER:
            return  # no format validation of the (unknown) data
        expected_fmt = self.defs[errstr]
        expected_type = type(expected_fmt)
        assert2(type(data) == expected_type, f'unexpected type {type(data)} for {data}, expected {expected_type}')
        if errstr == self.SUCCESS:
            assert2(data == self.defs[errstr])
        elif errstr == self.FAIL_PWROFF:
            assert2(all(x in self.valid_power_supplies for x in data))
        elif errstr == self.FAIL_BUSOFF:
            assert2(all(x in self.valid_canbus_ids for x in data))
        elif errstr == self.FAIL_TEMPLIMIT:
            for key, subdict in data.items():
                assert2(key in expected_fmt, f'unexpected key {key} in pc_response')
                if 'can' in key:
                    validate_numeric(subdict, key_type=int)
                elif key == 'other':
                    validate_numeric(subdict, key_type=object)
                else:
                    assert2(False, 'mismatch between expected_fmt and key-checking conditionals')
        elif errstr in {self.PARTIAL_SEND, self.FAIL_SEND}:
            for key, subdict in data.items():
                if key not in expected_fmt:
                    continue  # this is ok, for debug data, and we just skip any further validation
                for key2, subdata2 in subdict.items():
                    assert2(key2 in self.valid_canbus_ids, f'did not recognize bus id "{key2}"')
                    for x in subdata2:
                        assert2(pc.is_integer(x), f'unexpected non-integer canid "{x}"')
        if errstr in require_all_expected_keys:
            for key, value in expected_fmt.items():
                assert2(key in data, f'expected key {key}, but not found in pc_response')
    
    def simdata(self, case, tables):
        '''Generates simulated data matching a given case.
        
        INPUT:  case ... string defined in defs
                tables ... list of hardware-ready move tables
                
        OUTPUT: data formatted per defs
        '''
        err_frac = 0.5
        assert case in self.defs
        if case == self.SUCCESS:
            return self.defs[case]
        if case == self.FAIL_OTHER:
            return random.choice([{'hello': 'goodbye'}, ['some list'], 'some string', 666])
        if case in {self.FAIL_MOVERATE, self.FAIL_RESETRATE}:
            out = self.defs[self.FAIL_MOVERATE].copy()
            out['current_rate'] = 3601.0
            out['sec_until_ready'] = 1.0
            return out
        ids = {t['canid']: t['busid'] for t in tables}
        busids = set(ids.values())
        required = {t['canid'] for t in tables if t['required']}
        not_required = set(ids) - required
        if case in {self.FAIL_PWROFF, self.FAIL_BUSOFF}:
            if case == self.FAIL_PWROFF:
                population = [k for k, v in pc.power_supply_canbus_map.items() if busids & v]
            else:
                population = sorted(busids)
            num_fail = math.ceil(len(population) * err_frac)
            return random.sample(population, num_fail)
        if case == self.FAIL_TEMPLIMIT:
            num_fail = math.ceil(len(ids) * err_frac)
            fail_ids = random.sample(sorted(ids), num_fail)
            out = {}
            for canid, busid in ids.items():
                if canid not in fail_ids:
                    continue
                if busid not in out:
                    out[busid] = {}
                out[busid][canid] = 100.0
            out['other'] = {'FPP1': 200.0, 'FPP2': 1000}
            return out
        i = self.sim_subcases_last[case] + 1
        if i >= len(self.sim_subcases_cycle):
            i = 0
        self.sim_subcases_last[case] = i
        subcase = self.sim_subcases_cycle[i]
        out = {k: {} for k in self.defs[case]}
        if subcase == self.CLEARED:
            out[subcase] = {busid: [k for k, v in ids.items() if v == busid] for busid in busids}
            return out
        if case == self.PARTIAL_SEND:
            population = not_required
        else:
            population = required
        num_fail = math.ceil(len(population) * err_frac)
        fail_ids = random.sample(sorted(ids), num_fail)
        for i in ids:
            busid = ids[i]
            if i in fail_ids:
                if busid not in out[subcase]:
                    out[subcase][busid] = []
                out[subcase][busid].append(i)
            else:
                if busid not in out[self.CLEARED]:
                    out[self.CLEARED][busid] = []
                out[self.CLEARED][busid].append(i)
        out['extra1'] = 'extra dummy str data'
        out['extra2'] = [f'extra dummy list data {i}' for i in range(5)]
        return out
    
    def sim_cases_sequence(self):
        '''Return a list to do a complete sequence of simulated error cases.
        Some of the cases will be repeats, for which internally the simdata()
        function will cycle through subcases upon each iteration.
        '''
        seq = []
        for case in self.defs:
            if case in {self.PARTIAL_SEND, self.FAIL_SEND}:
                seq += [case] * len(self.sim_subcases_cycle)
            else:
                seq += [case]
        return seq
    
    def next_sim_case(self):
        '''Returns next case in the squence generated by sim_cases_sequence().
        Repeats from the beginning when it hits the end of the sequence. Note you
        will see repetitions of some cases. This is due to internal cycling of
        subcases within the simdata() function.
        '''
        self.sim_cases_last += 1
        if self.sim_cases_last >= len(self.sim_cases_cycle):
            self.sim_cases_last = 0
        return self.sim_cases_cycle[self.sim_cases_last]
    
    def sim_send_and_execute_tables(self, move_tables, case='SUCCESS'):
        '''For simulation. Replicates inputs/outputs of petalcomm function.
        Additional input argument 'case' should be one of the keys in this
        module's defs param.
        '''
        output = case, self.simdata(case, move_tables)
        sendex.validate(output)
        return output
    
# so you only have to initialize this once, in order to use the guts
sendex = SendExecCases()
printfunc = lambda x: print(f'test {x}')
sendex.printfunc = printfunc

if __name__ == '__main__':
    dummy_tables = []
    for i in range(5):
        this = {'canid': i,
                'busid': 'can11' if i % 2 else 'can12',
                'required': False if i % 2 else True}
        dummy_tables.append(this)
    cases = []
    simdata = []
    for i in range(len(sendex.sim_cases_cycle)):
        cases += [sendex.next_sim_case()]
        output = sendex.sim_send_and_execute_tables(dummy_tables, case=cases[-1])
        simdata += [output[1]]
    print(f'{len(cases)} cases self-validated')
    for i, case in enumerate(cases):
        print(f'\n{case}\n{"-"*len(case)}\n{simdata[i]}')
