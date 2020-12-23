import posconstants as pc
import random, math

class SendExecCases(object):
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
    def __init__(self):
        self.send_fail_format = {
            'cleared': dict,  # any pos for which move tables were originally defined, but whose memories are now known to be clear
            'no_response': dict,  # failed pos, which didn't respond on CAN bus. collection may overlap with cleared or unknown
            'unknown': dict,  # failed pos, which might or might not currently have tables loaded
            }  # subdicts have keys = busid strings like 'can11' etc and values = canid ints
        
        self.rate_fail_format = {
            'current_rate': float,  # foo per hour
            'sec_until_ready': float,  # min time (seconds) we must wait until ready again to execute
            }
        
        self.SUCCESS = 'SUCCESS'
        self.PARTIAL_SEND = 'PARTIAL SUCCESS: all required moves'
        self.FAIL_SEND = 'FAILED: sending tables'
        self.FAIL_PWROFF = 'FAILED: power off'
        self.FAIL_BUSOFF = 'FAILED: canbus off'
        self.FAIL_MOVERATE = 'FAILED: move rate limit'
        self.FAIL_RESETRATE = 'FAILED: power supply reset rate limit'
        self.FAIL_TEMPLIMIT = 'FAILED: temperature limit'
        
        self.defs = {
            self.SUCCESS:        None,  # all requested move tables sent and executed ok
            self.PARTIAL_SEND:   self.send_fail_format,  # any returned pos are in the failed-but-not-required category
            self.FAIL_SEND:      self.send_fail_format,  # return collections will contain some *required* pos for which tables failed to send
            self.FAIL_PWROFF:    [],  # list includes only the power supplies that are disabled
            self.FAIL_BUSOFF:    [],  # list includes only the can buses that are disabled
            self.FAIL_MOVERATE:  self.rate_fail_format,
            self.FAIL_RESETRATE: self.rate_fail_format,
            self.FAIL_TEMPLIMIT: {},  # keys = canids, values = temperatures. only includes the cases that exceed an acceptance threshold value
            }
        
        self.valid_power_supplies = {'PS1', 'PS2'}
        self.valid_canbus_ids = {f'can{i:02}' for i in range(100)} | {f'can{i}' for i in range(10)}
        
        self.sim_subcases_cycle = sorted(self.send_fail_format)
        self.sim_subcases_last = {self.PARTIAL_SEND: 0, self.FAIL_SEND: 0}            
            
    def validate(self, pc_response):
        '''Validates output from send_and_execute_tables() provided by petalcontroller.
        Throws an assertion if invalid, otherwise silent.
        '''
        def assert2(test):
            f'petalcontroller return data not understood:\n{pc_response}'
        assert2(len(pc_response) == 2)
        assert2(isinstance(pc_response, (tuple, list)))
        errstr = pc_response[0]
        data = pc_response[1]
        assert2(errstr in self.defs)
        expected_fmt = self.defs[errstr]
        expected_type = type(expected_fmt)
        assert2(type(data) == expected_type)
        if errstr == self.SUCCESS:
            assert2(data == self.defs[errstr])
        elif errstr == self.FAIL_PWROFF:
            assert2(all(x in self.valid_power_supplies for x in data))
        elif errstr == self.FAIL_BUSOFF:
            assert2(all(x in self.valid_canbus_ids for x in data))
        elif expected_type == dict and len(expected_fmt) > 0:
            for k, v in expected_fmt.items():
                assert2(k in data)
                assert2(isinstance(data[k], v))
    
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
            return {x: 100.0 for x in fail_ids}
        i = self.sim_subcases_last[case] + 1
        if i >= len(self.sim_subcases_cycle):
            i = 0
        self.sim_subcases_last[case] = i
        subcase = self.sim_subcases_cycle[i]
        out = {k: {} for k in self.defs[case]}
        if subcase == 'cleared':
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
                if busid not in out['cleared']:
                    out['cleared'][busid] = []
                out['cleared'][busid].append(i)
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
    
# so you only have to initialize this once, in order to use the guts
sendex = SendExecCases()

if __name__ == '__main__':
    dummy_tables = []
    for i in range(5):
        this = {'canid': i,
                'busid': 'can11' if i % 2 else 'can12',
                'required': False if i % 2 else True}
        dummy_tables.append(this)
    cases = sendex.sim_cases_sequence()
    simdata = []
    for case in cases:
        simdata += [sendex.simdata(case, dummy_tables)]
        sendex.validate((case, simdata[-1]))
    print(f'{len(cases)} cases self-validated')
    for i in range(len(cases)):
        print(f'\n{cases[i]}\n{"-"*len(cases[i])}\n{simdata[i]}')