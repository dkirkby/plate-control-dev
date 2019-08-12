"""
Kevin Fanning fanning.59@osu.edu

Test if targets in obsTP are overlapping/targeting a position occupied by another positioner

This works between a hypothetical 'left' and 'right' positioner spaced apart by the spacing
between petal holes 0 and 1 given in DESI-0329. This is useful for designing test cases for
anticollision and resonably ensuring they will not be rejected and frozen.
"""
import sys
import os
sys.path.append(os.path.abspath('../'))
import poscollider
import posmodel
import posstate

class OverlappingTargets():

	def __init__(self, posid1 = 'left', posid2 = 'right'):
		self.posid1 = posid1
		self.posid2 = posid2

		self.posstate1 = posstate.PosState(unit_id = self.posid1)
		self.posstate2 = posstate.PosState(unit_id = self.posid2)

		self.pos1 = posmodel.PosModel(state = self.posstate1)
		self.pos2 = posmodel.PosModel(state = self.posstate2)

		self.collider = poscollider.PosCollider()
		self.collider.add_positioners([self.pos1,self.pos2])

		self.collision_cases = ['Type I', 'Type II', 'Type IIIA', 'Type IIIB', 'GFA', 'PETAL']
		return

	def test_targets(self, left_target = None, right_target = None):
		if not(left_target):
			obst1 = input('Please enter the obs theta target for the left positioner: ')
			obsp1 = input('Please enter the obs phi target for the left positioner: ')
			left_target = [float(obst1), float(obsp1)]
		if not(right_target):
			obst2 = input('Please enter the obs theta target for the right positioner: ')
			obsp2 = input('Please enter the obs phi target for the right positioner: ')
			right_target = [float(obst2), float(obsp2)]
		collision_type = self.collider.spatial_collision_between_positioners(self.posid1, self.posid2, left_target, right_target)
		if collision_type == 0:
			print('No overlap in the targets, should be fine to send.')
			return self.collision_cases[collision_type]
		else:
			print('Collision', self.collision_cases[collision_type], 'detected. Target cannot be targeted.')
			if 'Type III' in self.collision_cases[collision_type]:
				print('A refers to the left positioner, B to the right. Type IIIA means that the phi arm of A is colliding with the body of B.')
			return self.collision_cases[collision_type]

if __name__ == '__main__':
	test = OverlappingTargets()
	test.test_targets()
