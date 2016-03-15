/*-------------------------------------------------------------------------------
 * Name:    Open_Loop_Test.c
 * Purpose: Generate R-Theta Positioner Waveforms in MCBSTM32E
 * Author:  hdh 
 
 *1.0			2015-1-25 		Reformatted move setup commands and data retrieval commands.  Added on-chip silicon id read-out command, variable acceleration (Spin Period),and the ability to set
 *											CAN address by writing it to flash with CAN commands (after verifying silicon id).  Added a second CAN filter so that all positioners can always respond to CAN messages 
 *											sent to this common address (20,000/0x4E20).  Added fiducial functionality.  Data request commands are now all separate commands.  (igershko)
 *
 *0.19	  2015-09-28		Added sync functionality  -- multiple CAN commands can be uploaded and are executed when a sync signal is received. 
 *											Changed CAN message filter and command decoding to expand the command type space 
 *											(from being the 4 LS bits to the 8 LS bits of the CAN message IDENTIFIER).  Added function for transmitting 
 *											CAN messages.  (igershko)  
 *
 *0.18a		2014-08-27		Changed heartbeat flash from PA4 to PA6 because that LED is connected on the Michigan board
 *
 *0.18		2013-06-23		Removed the pre-programmed sequences.  Put in defines REVMTR0 and REVMTR1 which allow the direction of motor
 *											rotation to be independently switched.  Added four flags: Bump_CW_Creep_Mtr_x and Bump_CCW_Creep_Mtr_x.  When 
 *											they are '1', the current is increased to 1.0 for the last 90 degrees of the creep.  Seems to be working OK.
 *											Added 4 parameters, MxCW_Drop_Cur for the value that each motor current drops to following a CW or CCW creep.
 *											Added Command 4 to set these values and the values of the Bump_CW_Creep_Mtr_x flags.
 *					
 *0.17b		2013-06-21		Work on crash and run forever if start with cruise = zero.  Replaced the entire timer ISR from "Do Motor_0 first
 *											to just before setting PA7 low  with the ISR from 0.13a.  Removed "FindStopStepsToGo" and replaced it with
 *											"CreepStepsToGo" everywhere.  Fixed bug in which the cruise and/or creep bits got stuck on if a move command was
 *											sent with Cruise or CreepStepsToGO set at zero (by adding a check in the service of command 5).
 *0.17a		2013-06-20  	Fixed problems with setting up PB5 which enables switches.  This is working in the prototype flight PCB.
 *											This still crashes if send a start when it is running
 *0.17		2013-06-18		This is continuing from version 0.09a.  I'm checking out BB-0200-01-v1
 *											
 *0.16		2013-04-22		This is intended to be used with prototype hardware made per BigBOSS-0173-v8 which   
 *											has the Hall effect sensors connected to GPIO pins as follows:
 *													Motor 0 Hall A to PC0 -- EXTI0						Motor 1 Hall A to PA3 -- EXTI3
 *													Motor 0 Hall B to PC1 -- EXTI1						Motor 1 Hall B to PC4 -- EXTI4
 *													Motor 0 Hall C to PC2 -- EXTI2						Motor 1 Hall C to PC5 -- EXTI5
 *											This allows all Halls to connect to falling edge sensitive interrupts with unique
 *											ISR vectors. The Keil MCBSTM32F breadboard based system does not (currently) have
 *											these connections.  Removed the pre-programmed sequences (which use some of the same 
 *											EXTI resources).
 *
 *0.15		2013-03-20		This has the same pre-programmed sequences, but now based on the 280.078205 gear ratio
 *											of the Maxon motor,  and pre-programmed sequences operate motor 1.
 *														Request			Actual
 *														330					329.9999726
 *														180					180.0000825
 *														 90					 89.9998627
 *														 30					 29.99983522
 *															1						1.000077817
 *															0.04				0.039988831
 *
 *0.14		2013-03-18		Put the pre-programmed sequences back in.  This has values for making Joes requested
 *											moves based on the 337.3594336 gear ratio of the Namiki motor.  Programmed sequences
 *											operate motor 0.   Fixed mistake in cases 12 thru 15.
 *														Request			Actual
 *														330					329.9999612
 *														180					180.0000058
 *														 90					 89.99985469
 *														 30					 30.00005037
 *															1						1.000120247
 *															0.04				0.040016667
 *
 *0.13b		2013-03-17		Put the pre-programed sequences back in.  Changed them to operate Motor_1.
 *											On 2013-06-17 this doesn't work.  Crashes when SELECT is pressed.
 *
 *0.13a		2013-03-15		Improved the code for automatically backing off the motor current following a spin-down or a creep.
 *
 *0.13		2013-03-15		Removed all the stuff for pre-programmed sequences.
 *
 *0.12		2013-03-10		This adds code to increase the current to 100% of stall for the last 90 degrees of
 *										  a CW creep.  At the end of a CW creep it sets that motor current to zero by setting
 *											the TIMx_CCRx to zero.
 *
 *0.11		2013-02-27		This is a special case made with some pre-programmed routines requested by Joe & Bobby
 *
 *0.10		2013-02-25		Added some more pre-programmed motions to accomodate the 4mm motor
 *
 *0.09a		2013-06-17		For some reason 0.09 doesn't seem to respond to CAN messages.  This is an attempt to fix it.
 *											CAN code was not complete.  Fixed it.  Also added cycling of LED's on PA4-7  (see line 159 and
 *											5 lines at the top of the timer ISR,  and nat line 871)
 *											This now seems to run in both the MCBSTM32E and in BB-0200-01-v1.  I am now going to freeze this
 *											and continue development and checkout of the BB-0200 with rev 0.17
 *
 *0.09		2013-02-23		Removed the LCD Display stuff which seems to interfere with the motor control.
 *											Added code to pulse PB14 for 1/2 a second when a CAN message which gets through the
 *											filter is received.  Cleaned up stuff a little.
 *
 *0.08		2013-02-23		This version adds control of the motors from CAN messages generated by the program 
 *											Positioner_Controller.cpp which runs in a Windows PC which has a Lawicel CANUSB module
 *											installed.  It was made by basically adding the CAN_Demo_2 code which includes display of
 *											the CAN message contents on the LCD display, to version 0.07.This will enable control of 100
 *											or so postitioners simultaneously by putting them in parallel on a bus with the CANUSB.
 *											Positioner_Controller is currently at Rev 0.01.  
 *											A description of the command structure is included at the beginning of the source code listing
 *											for that program.
 *
 *0.07a		2013-06-10		This is a special version on 0.07 used to test the first B-0200-01-v1 board. It cycles the LED's.
 *
 *0.07		2013-02-23		This is a working version which successfully operates two motors using pre-programmed routines
 *											which are selected using I/O buttons and the LED readout on the MCSSTM32E evaluation board.  
 *											Note that there were a bunch of bugs in the pre-programmed test routines in the earlier versions
 *											(e.g. CCW and CW interchanged),  so use this one for pre-programmed routines.
 *											It does not have the CAN interface implemented.  That will be done in version 0.08.
 *
 *0.06		2013-01-15		0.05 doesn't work because the M3 can't do even a single cosine in the 55 u-sec interrupt period.  So this
 *											version will use a more accurate cosine table and will try to minimize processor load in the ISR.
 *
 *0.05		2013-01-07		Will try re-writng the higher speed motions using floating point numbers and trig functions
 *											to get better resolution and a more accurate control of the spin-up profile.
 *
 *0.04		2012-12-19		Adds capability to select from a group of test routines using the joy stick on the MCBSTM32E.
 *											UP is PG15  --  EXTI15 > EXTI15_10_IRQn=40;  DOWN is PD3  --  EXTI3 > EXTI3_IRQn=9;
 *											SELECT is PG7  --  EXTI7 > EXTI9_5_IRQn=23;  All switches have pull up resistors.
 *											Use DOWN to increment 4 bits which are displayed as bits 8 through 11 on the LED's connected
 *											to PB on the MCBSTM32E.  UP decrements the number.  SELECT executes the test routine
 *											corresponding to the displayed number.  This is for testing only and will not be included in
 *											the flight version.  Works great for the low speed operations, but seems to not keep up at 10,000 RPM.
 *
 *0.03		2012-12-18		Add the code I wrote previously which generates the motor control waveforms.
 *											It doesn't make use of any of the CAN stuff yet.
 *											This is intended to control a pair of a Faulhaber Series 0620-012B Brushless DC motors used
 *											in the LBNL R-Theta robotic fiber positioner.
 *											The controller will be open loop with the motor field rotated the desired number of radians,
 *											to get the positioner where it is wanted. (The overall loop is closed via the Fiber View Camera.)
 *											To avoid backlash effects, the desired postion will always be approched from one direction 
 *											(CCW) with no overshoot.
 *
 *											Some motor parameters:
 *											Winding topology:												3 Pole Delta
 *											Phase to phase terminal resistance:			59.0 Ohms
 *											Stall Torque:														5.7E-4 Nm
 *											Static Friction Torque:									2.3E-5 Nm
 *											Back EMF Const.:												3.05E-4 V/RPM
 *											Torque Constant:												344 A/Nm
 *											Rotor Inertia:													9.5E-10 Kg-m^2
 *											Angular Acceleration at Stall Current:	6.01E5 rad/sec^2
 *						
 *											The processor clock is set to 72 MHz.  A timer provides a continuous Interrupt at
 *											72,000,000/4,001 = ~17,996 Hz.  This signal starts TIM1 and TIM8, the "advanced control"
 *											timers, one for each motor.  Each Timer has 3 comparator outputs generating Tau_1, Tau_2 and 
 *											Tau_3, each of which drives one pole of an Analog Devices ADG1636 2-pole half bridge which drives   
 *											one motor phase.  Variables Theta _0 and Theta_1 specify the rotor phase of each motor. Normally 
 *											Theta is constant so the Tau do not change and the motors do not rotate.  When it is desired to 
 *											move a positioner, the motors are each rotated through a phase specified to 1 degree.
 *											Movement of a motor is done in 4 steps: 1)Spin_Up from 0 to 10,000 RPM which is done at full stall
 *											current, but with only 1/3 of the nomial acceleration (to provide a 3X torque margin) which
 *											takes 173 degrees, 2)Cruising at 10,000 RPM for the interger number of degrees modulo 30 you specify 
 *											3)Spin_Down to zero  4)Creep the last ~two rotations at 1 degree per step to the final specified 
 *											phase.  (So as eliminate inertial effects, take up backlash, and trim to the exact number of degrees wanted.)
 *											When the motion is complete, voltage to the motors is turned off.  There may be some cogging
 *											of the rotors at that time (the motors have a weak 2 position cogging).  When the voltage is turned 						
 *											back on, the motors will come back to the phase where they were left, because the Tau's have not changed.
 *											This works! I put a small block of test code just before the while(1) in main to run motor_0 first
 *											against the stop, and then to creep forward.
 *
 *0.02		2012-12-02		Cut back to just TIM1 and TIM8 and added a dummy TIM1 Update Interrupt
 *											which flashes PB15 at a little less than 1 Hz; i.e. the interrupts work!
 * 
 *0.01		2012-12-01  	First attempt to operate the Cortex-M3 MCU STM32F103RCY6.  This has 4 timers working at 20KHz,
 *											each with 4 compare outputs to generate PWM waveforms (Need only 2 timers with 3 compare outputs on each).  
 *											I started with Keil's CAN example for the MCBSTM32E and then eliminated everything but the stuff 
 *											needed for CAN and then added what was needed for the timers.
 *
 *	NOTE: References to a particular page number refer to the RM0008 Reference Manual for the STM32F101xx, STM32F102xx, STM32F103xx, 
 *        STM32F105xx and STM32F107xx advanced ARM-based 32-bit MCUs  made by ST Micro.  It is available at www.st.com
 *
 *-----------------------------------------------------------------------------*/
/*%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%%%%%%%%%%%%% INSTRUCTIONS FOR DOING A MOVE OF BOTH POSITIONER MOTORS %%%%%%%%%%
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
>>>>First make sure the following have the values you want:
These values remain constant after a motor rotation
Spin_Ptr_0 = 0						
Spin_Ptr_1 = 0
CW_CreepPeriod_0
CW_CreepPeriod_1
CCW_CreepPeriod_0
CCW_CreepPeriod_1
CruiseCurrent_0
SpinUpCurrent_0 
SpinDownCurrent_0 
CreepCurrent_0 
CreepCurrent_0
CruiseCurrent_1 
SpinUpCurrent_1
SpinDownCurrent_1
CreepCurrent_1
CreepCurrent_1

>>>>Then set up these based on how many degrees of rotation you want from each motor:
These values go to zero as a part of the motor rotation
CruiseStepsToGo_0 
CW_CreepStepsToGo_0 
CCW_CreepStepsToGo_0
CruiseStepsToGo_1
CW_CreepStepsToGo_1 
CCW_CreepStepsToGo_1

>>>>Then set the Shadow Flags Sh_Fl_0 and Sh_Fl_1,  and finally set Flags_Set = 1

At the next timer update interrupt it will transfer the contents of the shadow flags
to Flags_0 and Flags_1 and then the motor(s) will begin rotation
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%*/

 /*******************************************************
 * 		     Header Files
 ******************************************************/
#include <stdio.h>
#include "stm32f10x.h"                            // Their STM32F10x Definitions (most of which I am not using) 
#include "CAN.h"                                  // STM32 CAN adaption layer
#include "ADC.h"
#include "STM32F103_Registers.h"   								// My file with register location defines
#include "FlashOS.H"
    

 //  Left from Keil's CAN example  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
volatile uint32_t msTicks;                        /* counts 1ms timeTicks     */
 //  Left from Keil's CAN example  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

/*******************************************************
 * 		     Global Variables
 *******************************************************/

#define M16(adr) (*((vu16 *) (adr)))
 
#define REVMTR0 1								//  '0' for normal motor 0 operation;  '1' to reverse the direction of motor 0 operation
#define REVMTR1 1								//  '0' for normal motor 1 operation;  '1' to reverse the direction of motor 1 operation

unsigned int DEL0A = 1200 * (1+REVMTR0);  //  These set the phase difference between the current in each motor phase as so
unsigned int DEL0B = 2400 / (1+REVMTR0);  //  control the direction of the motor rotation

unsigned int DEL1A = 1200 * (1+REVMTR1);
unsigned int DEL1B = 2400 / (1+REVMTR1);
 

#define Offset_0 0							//  These are two offsets which are measured and recorded for each positioner 
#define Offset_1 0							//  which specify the phase of the rotors when they are nominally up against the hard stops

#define TIMDIV 4000							//  Timer Divide number. This is the number that Timers TIM1 and TIM8 divide by.  So interrupt rate is 
																//	72,000,000/TIMDIV = 18,000 Hz, and the period is 1/18,000 = .0000555555555 seconds
#define FIRMWARE_VR   10
 
int LED_Clock = 0;					 		// output this to PA4;  used to blink LED			
int done=0;
int set_can_id=0;
int stack_size=100;							// variable for keeping track of movetable size


CAN_msg CAN_Com_Stack[100];			// storage structure of movetable commands

unsigned int count = 0;					//  Counts the number of times the Timer ISR has been executed so as to control the creep rate	

unsigned int post_pause=0;
unsigned int period=0;					//	Length of time during which fiducials remain on after receiving sync signal

unsigned char Flags_0 = 0;			//	One flag for each motor specifies which rotation elements are pending or in process  
																//  Bit 7(MSB):  CW Spin_Up of Motor 0 Pending or in process
																//  Bit 6:  CW Cruise of Motor 0 pending or in process
																//  Bit 5:  CW Spin_Down of Motor 0 pending or in process
																//  Bit 4:  CCW Spin_Up of Motor 0 Pending or in process
																//  Bit 3:  CCW Cruise of Motor 0 pending or in process
																//  Bit 2:  CCW Spin_Down of Motor 0 pending or in process
																//  Bit 1:  CCW Low current creep against stop for motor 0
																//  Bit 0:  CW Creep to final position for motor 0
																//  When  the interrupt is serviced, the function corresponding to the most significant
																//  bit in Flag_0 will be active
									
unsigned char Flags_1 = 0;
																//  Bit 7:  CW Spin_Up of Motor 1 Pending or in process
																//  Bit 6:  CW Cruise of Motor 1 pending or in process
																//  Bit 5:  CW Spin_Down of Motor 1 pending or in process
																//  Bit 4:  CCW Spin_Up of Motor 1 Pending or in process
																//  Bit 3:  CCW Cruise of Motor 1 pending or in process
																//  Bit 2:  CCW Spin_Down of Motor 1 pending or in process
																//  Bit 1:  CCW Low current creep to stop for motor 1
																//  Bit 0:  CW Creep to final position of motor 1
									
unsigned char Sh_Fl_0 = 0;			//  Shadow register. This is transferred into Flags_0 at the end of the next up date interrupt after Set_Flags is set = 1
unsigned char Sh_Fl_1 = 0;			//  This is transferred into Flags_1 at the end of the next up date interrupt after Set_Flags is set = 1 
unsigned char Set_Flags = 0;		//  Set this to one to initiate transfer of shadow data into the Flags
unsigned char Set_Flags_0 = 0;
unsigned char Set_Flags_1 = 0;

unsigned char Flag_Status_0=0;	//  Keep track of whether flags need to be set for Motor 0, Motor 1, or both for independent operation of axes in move table
unsigned char Flag_Status_1=0;

unsigned char run_test_seq=0;		//  Flag set for sending test patterns to theta/phi pads for testing positioner board (prior to installing motors)
unsigned char device_type=0;
																
unsigned int Theta_0 = Offset_0;//  Phase of rotor of motor 0 in 0.1 degree steps --  takes interger values between 0 and 3600
unsigned int Theta_1 = Offset_1;//  Phase of rotor of motor 1
float duty_cycle=0;

char Bump_CW_Creep_Mtr_0 = 1;		//  If this flag is set, the corresponding creep current is increased to 1.0 for the last 90 deg of motor rotation
char Bump_CCW_Creep_Mtr_0 = 0;	//
char Bump_CW_Creep_Mtr_1 = 1;		//
char Bump_CCW_Creep_Mtr_1 = 0;	//

/* -----------------------------------------------------------------------------------------------------
Assignment of motor phases to I/O pins on PCB P/N BB-0135-v2  --  Note there is no "remapping" of timer outputs
MTR_0 Phase A  --  PA11			TIM1_CH4			Tau0_1
MTR_0 Phase B  --  PA9			TIM1_CH2			Tau0_2
MTR_0 Phase C  --  PA10			TIM1_CH3			Tau0_3
MTR_1 Phase A  --  PC6			TIM8_CH1			Tau1_1
MTR_1 Phase B  --  PC7			TIM8_CH2			Tau1_2
MTR_1 Phase C  --  PC8			TIM8_CH3			Tau1_3
									 PA8 is set to have a 15/40 duty cycle just to show that the timers are set up
                   PC4 used as enable for the motor switches  (On MCBSTM32E version only)
									 PB15 is used as a sync for checking ISR operation.  It is high while in the Timer Update ISR.
									 PB14 is pulsed high to when SELECT is pressed  (On MCBSTM32E version only)
									 //PB10-13 show the current value of prog_nr    (On MCBSTM32E version only)
									 PB8 and PB9 are used by the CAN interface and are usually high				   
----------------------------------------------------------------------------------------------------- */

unsigned int pos_id=65535;								//  This is the can address that all positioners will initially have
unsigned int Spin_Ptr_0 = 0;							//  Pointer into Spin_Up table for motor 0
unsigned int Spin_Ptr_1 = 0;							//  Pointer into Spin_Up table for motor 1
unsigned int CruiseStepsToGo_0 = 3000;		//  Number of remaining 30 degree steps left in a cruise for motor 0
unsigned int CruiseStepsToGo_1 = 3000;		//  Number of remaining 30 degree steps left in a cruise for motor 1

unsigned int CW_CreepStepsToGo_0 = 40000;	//  Number of remaining CW creep steps left for motor 0  
unsigned int CW_CreepStepsToGo_1 = 40000;	//  Number of remaining CW creep steps left for motor 1

unsigned int CCW_CreepStepsToGo_0 = 40000;//  Number of remaining CCW creep steps left for motor 0  
unsigned int CCW_CreepStepsToGo_1 = 40000;//  Number of remaining CCW creep steps left for motor 1

unsigned int CreepPeriod_0 = 2;				//  Number Timer Update cycles for each advance of 0.1 degree when creeping
unsigned int CreepPeriod_1 = 2;				//  The creep has a basic rotation rate of 0.1 degree per Timer update
																					//	which is 18000/3600 = 300 RPM.  So the rotation rate in RPM is 300/CW_CreepPeriod or CCW_CreepPeriod


unsigned int count_0 = 0;							//  Creep count for motor 0  --  this keeps track of how many times it's gone through the interrupt without incrementing the motor
unsigned int count_1 = 0;							//  Creep count for motor 1  --  same as above but for motor 1
unsigned int data=0;
unsigned int data_upper=0;
unsigned int bit_sum=0;								//Received move table bit sum
unsigned int bit_sum_match=0;					//Flag indicating if sent bit sum and received bit sum match

unsigned int move_table_status=0;
unsigned int Spin_Period=12;
unsigned int spin_count_0=0;
unsigned int spin_count_1=0;
unsigned int legacy_test_mode = 0;

// The following currents set the motor current in units of full stall current, so 1 corresponds to 100% or fully on, i.e. about 200 mA

float CruiseCurrent_0 = .75;					//  Value of current used along with the desired phase when calculating
float SpinUpCurrent_0 = 1;						//  Tau's for motors.  CruiseCurrent = 4 makes the voltages on the motor coils 
float SpinDownCurrent_0 = 1;					//  swing from 0 to full motor voltage, i.e. it makes Tau go to 4,000 at the peak

float CreepCurrent_0 = .3;						//  Current for CW Creep for Motor 0  (i.e. forward)
float CW_OpCreepCur_0 = 0;						//  This is the current used during a CW creep operation.  It is set to CreepCurrent_0
																			//  at the beginning of a move, and then if the flag Bump_CW_Creep_Mtr_0 is set, it is bumped up to 1.0
																			//  for the last 90 degrees of the creep to get as close to the target as possible
																			

float CCW_OpCreepCur_0 = 0;						//  This is the current used during a CCW creep operation.  It is set to CreepCurrent_0
																			//  at the beginning of a move, and then if the flag Bump_CCW_Creep_Mtr_0 is set, it is bumped up to 1.0
																			//  for the last 90 degrees of the creep to get as close to the target as possible

float CruiseCurrent_1 = .75;					//  Current when cruising
float SpinUpCurrent_1 = 1;						//  Current when Spinning Up
float SpinDownCurrent_1 = 1;					//  Current when Spinning Down

float CreepCurrent_1 = .3;						//  Current for CW Creep for Motor 1  (i.e. forward)
float CW_OpCreepCur_1 = 0;						//  See comments for CW_OpCreepCur_0 above

float CCW_OpCreepCur_1 = 0;						//

float M0_Drop_Cur = .05;							//  Following a creep, the motor current is dropped to this value
float M1_Drop_Cur = .05;


//  Tau = (Current (values 0 thru 1)) * Cos(phase)  (values 0 thru 4000) with maximum 4,000.
//  Timers are set to count up to 4,000 and then they are automatically updated to 0 by hardware.
//  This gives 4000 counts corresponding to the cosine of the motor phase.  

//  For cosine table, index is units of 0.1 degree with the table entries normalized to be 0 to 4000
//  It goes out to >600 degrees so I only have to check for roll-over once during each interrupt
static unsigned short CosTable[6144]=
{
4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3998, 	3998, 	3998, 	3998, 	3998, 	3998, 	3997, 	3997, 	3997, 	3997, 	3997, 	3996, 	3996, 	3996, 	3996, 	3996, 	3995, 	3995, 	3995, 	3995, 	3994, 	3994, 	3994, 	3994, 	3993, 	3993, 	3993, 	3992, 	3992, 	3992, 	3991, 	3991, 	3991, 	3990, 	3990, 	3990, 	3989, 	3989, 	3989, 	3988, 	3988, 	3988, 	3987, 	3987, 	3986, 	3986, 	3986, 	3985, 	3985, 	3984, 	3984, 	3983, 	3983, 	3982, 	3982, 	3981, 	3981, 	3981, 	3980, 	3980, 	3979, 	3979, 	3978, 	3978, 	3977, 	3976, 	3976, 	3975, 	3975, 	3974, 	3974, 	3973, 	3973, 	3972, 	3971, 	3971, 	3970, 	3970, 	3969, 	3968, 	3968, 	3967, 	3967, 	3966, 	3965, 	3965, 	3964, 	3963, 	3963, 	3962, 	3961, 	3961, 	3960, 	3959, 	3958, 	3958, 	3957, 	3956, 	3956, 	3955, 	3954, 	3953, 	3953, 	3952, 	3951, 	3950, 	3950, 	3949, 	3948, 	3947, 	3946, 	3946, 	3945, 	3944, 	3943, 	3942, 	3941, 	3941, 	3940, 	3939, 	3938, 	3937, 	3936, 	3935, 	3935, 	3934, 	3933, 	3932, 	3931, 	3930, 	3929, 	3928, 	3927, 	3926, 	3925, 	3924, 	3923, 	3923, 	3922, 	3921, 	3920, 	3919, 	3918, 	3917, 	3916, 	3915, 	3914, 	3913, 	3912, 	3911, 	3910, 	3908, 	3907, 	3906, 	3905, 	3904, 	3903, 	3902, 	3901, 	3900, 	3899, 	3898, 	3897, 	3896, 	3894, 	3893, 	3892, 	3891, 	3890, 	3889, 	3888, 	3886, 	3885, 	3884, 	3883, 	3882, 	3881, 	3879, 	3878, 	3877, 	3876, 	3875, 	3873, 	3872, 	3871, 	3870, 	3868, 	3867, 	3866, 	3865, 	3863, 	3862, 	3861, 	3860, 	3858, 	3857, 	3856, 	3854, 	3853, 	3852, 	3850, 	3849, 	3848, 	3846, 	3845, 	3844, 	3842, 	3841, 	3840, 	3838, 	3837, 	3836, 	3834, 	3833, 	3831, 	3830, 	3829, 	3827, 	3826, 	3824, 	3823, 	3821, 	3820, 	3818, 	3817, 	3816, 	3814, 	3813, 	3811, 	3810, 	3808, 	3807, 	3805, 
3804, 	3802, 	3801, 	3799, 	3798, 	3796, 	3795, 	3793, 	3791, 	3790, 	3788, 	3787, 	3785, 	3784, 	3782, 	3780, 	3779, 	3777, 	3776, 	3774, 	3772, 	3771, 	3769, 	3768, 	3766, 	3764, 	3763, 	3761, 	3759, 	3758, 	3756, 	3754, 	3753, 	3751, 	3749, 	3748, 	3746, 	3744, 	3742, 	3741, 	3739, 	3737, 	3736, 	3734, 	3732, 	3730, 	3729, 	3727, 	3725, 	3723, 	3721, 	3720, 	3718, 	3716, 	3714, 	3713, 	3711, 	3709, 	3707, 	3705, 	3703, 	3702, 	3700, 	3698, 	3696, 	3694, 	3692, 	3691, 	3689, 	3687, 	3685, 	3683, 	3681, 	3679, 	3677, 	3675, 	3674, 	3672, 	3670, 	3668, 	3666, 	3664, 	3662, 	3660, 	3658, 	3656, 	3654, 	3652, 	3650, 	3648, 	3646, 	3644, 	3642, 	3640, 	3638, 	3636, 	3634, 	3632, 	3630, 	3628, 	3626, 	3624, 	3622, 	3620, 	3618, 	3616, 	3614, 	3612, 	3610, 	3608, 	3606, 	3604, 	3601, 	3599, 	3597, 	3595, 	3593, 	3591, 	3589, 	3587, 	3585, 	3582, 	3580, 	3578, 	3576, 	3574, 	3572, 	3570, 	3567, 	3565, 	3563, 	3561, 	3559, 	3556, 	3554, 	3552, 	3550, 	3548, 	3545, 	3543, 	3541, 	3539, 	3537, 	3534, 	3532, 	3530, 	3528, 	3525, 	3523, 	3521, 	3519, 	3516, 	3514, 	3512, 	3509, 	3507, 	3505, 	3503, 	3500, 	3498, 	3496, 	3493, 	3491, 	3489, 	3486, 	3484, 	3482, 	3479, 	3477, 	3475, 	3472, 	3470, 	3467, 	3465, 	3463, 	3460, 	3458, 	3456, 	3453, 	3451, 	3448, 	3446, 	3444, 	3441, 	3439, 	3436, 	3434, 	3431, 	3429, 	3427, 	3424, 	3422, 	3419, 	3417, 	3414, 	3412, 	3409, 	3407, 	3404, 	3402, 	3399, 	3397, 	3394, 	3392, 	3389, 	3387, 	3384, 	3382, 	3379, 	3377, 	3374, 	3372, 	3369, 	3367, 	3364, 	3361, 	3359, 	3356, 	3354, 	3351, 	3349, 	3346, 	3343, 	3341, 	3338, 	3336, 	3333, 	3330, 	3328, 	3325, 	3323, 	3320, 	3317, 	3315, 	3312, 	3309, 	3307, 	3304, 	3302, 	3299, 	3296, 	3294, 	3291, 	3288, 	3286, 	3283, 	3280, 	3278, 	3275, 	3272, 	3269, 	3267, 	3264, 	3261, 	3259, 	3256, 
3253, 	3250, 	3248, 	3245, 	3242, 	3240, 	3237, 	3234, 	3231, 	3229, 	3226, 	3223, 	3220, 	3218, 	3215, 	3212, 	3209, 	3206, 	3204, 	3201, 	3198, 	3195, 	3192, 	3190, 	3187, 	3184, 	3181, 	3178, 	3176, 	3173, 	3170, 	3167, 	3164, 	3161, 	3159, 	3156, 	3153, 	3150, 	3147, 	3144, 	3141, 	3139, 	3136, 	3133, 	3130, 	3127, 	3124, 	3121, 	3118, 	3115, 	3113, 	3110, 	3107, 	3104, 	3101, 	3098, 	3095, 	3092, 	3089, 	3086, 	3083, 	3080, 	3078, 	3075, 	3072, 	3069, 	3066, 	3063, 	3060, 	3057, 	3054, 	3051, 	3048, 	3045, 	3042, 	3039, 	3036, 	3033, 	3030, 	3027, 	3024, 	3021, 	3018, 	3015, 	3012, 	3009, 	3006, 	3003, 	3000, 	2997, 	2994, 	2991, 	2988, 	2985, 	2982, 	2979, 	2976, 	2973, 	2970, 	2967, 	2964, 	2960, 	2957, 	2954, 	2951, 	2948, 	2945, 	2942, 	2939, 	2936, 	2933, 	2930, 	2927, 	2923, 	2920, 	2917, 	2914, 	2911, 	2908, 	2905, 	2902, 	2899, 	2896, 	2892, 	2889, 	2886, 	2883, 	2880, 	2877, 	2874, 	2870, 	2867, 	2864, 	2861, 	2858, 	2855, 	2852, 	2848, 	2845, 	2842, 	2839, 	2836, 	2833, 	2829, 	2826, 	2823, 	2820, 	2817, 	2813, 	2810, 	2807, 	2804, 	2801, 	2797, 	2794, 	2791, 	2788, 	2785, 	2781, 	2778, 	2775, 	2772, 	2769, 	2765, 	2762, 	2759, 	2756, 	2752, 	2749, 	2746, 	2743, 	2739, 	2736, 	2733, 	2730, 	2727, 	2723, 	2720, 	2717, 	2713, 	2710, 	2707, 	2704, 	2700, 	2697, 	2694, 	2691, 	2687, 	2684, 	2681, 	2677, 	2674, 	2671, 	2668, 	2664, 	2661, 	2658, 	2654, 	2651, 	2648, 	2645, 	2641, 	2638, 	2635, 	2631, 	2628, 	2625, 	2621, 	2618, 	2615, 	2611, 	2608, 	2605, 	2601, 	2598, 	2595, 	2591, 	2588, 	2585, 	2581, 	2578, 	2575, 	2571, 	2568, 	2565, 	2561, 	2558, 	2555, 	2551, 	2548, 	2545, 	2541, 	2538, 	2534, 	2531, 	2528, 	2524, 	2521, 	2518, 	2514, 	2511, 	2508, 	2504, 	2501, 	2497, 	2494, 	2491, 	2487, 	2484, 	2480, 	2477, 	2474, 	2470, 	2467, 	2463, 	2460, 
2457, 	2453, 	2450, 	2447, 	2443, 	2440, 	2436, 	2433, 	2429, 	2426, 	2423, 	2419, 	2416, 	2412, 	2409, 	2406, 	2402, 	2399, 	2395, 	2392, 	2388, 	2385, 	2382, 	2378, 	2375, 	2371, 	2368, 	2364, 	2361, 	2358, 	2354, 	2351, 	2347, 	2344, 	2340, 	2337, 	2334, 	2330, 	2327, 	2323, 	2320, 	2316, 	2313, 	2309, 	2306, 	2303, 	2299, 	2296, 	2292, 	2289, 	2285, 	2282, 	2278, 	2275, 	2271, 	2268, 	2265, 	2261, 	2258, 	2254, 	2251, 	2247, 	2244, 	2240, 	2237, 	2233, 	2230, 	2226, 	2223, 	2219, 	2216, 	2213, 	2209, 	2206, 	2202, 	2199, 	2195, 	2192, 	2188, 	2185, 	2181, 	2178, 	2174, 	2171, 	2167, 	2164, 	2160, 	2157, 	2153, 	2150, 	2146, 	2143, 	2140, 	2136, 	2133, 	2129, 	2126, 	2122, 	2119, 	2115, 	2112, 	2108, 	2105, 	2101, 	2098, 	2094, 	2091, 	2087, 	2084, 	2080, 	2077, 	2073, 	2070, 	2066, 	2063, 	2059, 	2056, 	2052, 	2049, 	2045, 	2042, 	2038, 	2035, 	2031, 	2028, 	2024, 	2021, 	2017, 	2014, 	2010, 	2007, 	2003, 	2000, 	1997, 	1993, 	1990, 	1986, 	1983, 	1979, 	1976, 	1972, 	1969, 	1965, 	1962, 	1958, 	1955, 	1951, 	1948, 	1944, 	1941, 	1937, 	1934, 	1930, 	1927, 	1923, 	1920, 	1916, 	1913, 	1909, 	1906, 	1902, 	1899, 	1895, 	1892, 	1888, 	1885, 	1881, 	1878, 	1874, 	1871, 	1867, 	1864, 	1860, 	1857, 	1854, 	1850, 	1847, 	1843, 	1840, 	1836, 	1833, 	1829, 	1826, 	1822, 	1819, 	1815, 	1812, 	1808, 	1805, 	1801, 	1798, 	1794, 	1791, 	1787, 	1784, 	1781, 	1777, 	1774, 	1770, 	1767, 	1763, 	1760, 	1756, 	1753, 	1749, 	1746, 	1742, 	1739, 	1735, 	1732, 	1729, 	1725, 	1722, 	1718, 	1715, 	1711, 	1708, 	1704, 	1701, 	1697, 	1694, 	1691, 	1687, 	1684, 	1680, 	1677, 	1673, 	1670, 	1666, 	1663, 	1660, 	1656, 	1653, 	1649, 	1646, 	1642, 	1639, 	1636, 	1632, 	1629, 	1625, 	1622, 	1618, 	1615, 	1612, 	1608, 	1605, 	1601, 	1598, 	1594, 	1591, 	1588, 	1584, 	1581, 	1577, 	1574, 
1571, 	1567, 	1564, 	1560, 	1557, 	1553, 	1550, 	1547, 	1543, 	1540, 	1537, 	1533, 	1530, 	1526, 	1523, 	1520, 	1516, 	1513, 	1509, 	1506, 	1503, 	1499, 	1496, 	1492, 	1489, 	1486, 	1482, 	1479, 	1476, 	1472, 	1469, 	1466, 	1462, 	1459, 	1455, 	1452, 	1449, 	1445, 	1442, 	1439, 	1435, 	1432, 	1429, 	1425, 	1422, 	1419, 	1415, 	1412, 	1409, 	1405, 	1402, 	1399, 	1395, 	1392, 	1389, 	1385, 	1382, 	1379, 	1375, 	1372, 	1369, 	1365, 	1362, 	1359, 	1355, 	1352, 	1349, 	1346, 	1342, 	1339, 	1336, 	1332, 	1329, 	1326, 	1323, 	1319, 	1316, 	1313, 	1309, 	1306, 	1303, 	1300, 	1296, 	1293, 	1290, 	1287, 	1283, 	1280, 	1277, 	1273, 	1270, 	1267, 	1264, 	1261, 	1257, 	1254, 	1251, 	1248, 	1244, 	1241, 	1238, 	1235, 	1231, 	1228, 	1225, 	1222, 	1219, 	1215, 	1212, 	1209, 	1206, 	1203, 	1199, 	1196, 	1193, 	1190, 	1187, 	1183, 	1180, 	1177, 	1174, 	1171, 	1167, 	1164, 	1161, 	1158, 	1155, 	1152, 	1148, 	1145, 	1142, 	1139, 	1136, 	1133, 	1130, 	1126, 	1123, 	1120, 	1117, 	1114, 	1111, 	1108, 	1104, 	1101, 	1098, 	1095, 	1092, 	1089, 	1086, 	1083, 	1080, 	1077, 	1073, 	1070, 	1067, 	1064, 	1061, 	1058, 	1055, 	1052, 	1049, 	1046, 	1043, 	1040, 	1036, 	1033, 	1030, 	1027, 	1024, 	1021, 	1018, 	1015, 	1012, 	1009, 	1006, 	1003, 	1000, 	997, 	994, 	991, 	988, 	985, 	982, 	979, 	976, 	973, 	970, 	967, 	964, 	961, 	958, 	955, 	952, 	949, 	946, 	943, 	940, 	937, 	934, 	931, 	928, 	925, 	922, 	920, 	917, 	914, 	911, 	908, 	905, 	902, 	899, 	896, 	893, 	890, 	887, 	885, 	882, 	879, 	876, 	873, 	870, 	867, 	864, 	861, 	859, 	856, 	853, 	850, 	847, 	844, 	841, 	839, 	836, 	833, 	830, 	827, 	824, 	822, 	819, 	816, 	813, 	810, 	808, 	805, 	802, 	799, 	796, 	794, 	791, 	788, 	785, 	782, 	780, 	777, 	774, 	771, 
 769, 	 766, 	 763, 	 760, 	 758, 	 755, 	 752, 	 750, 	 747, 	 744, 	 741, 	 739, 	 736, 	 733, 	 731, 	 728, 	 725, 	 722, 	 720, 	 717, 	 714, 	 712, 	 709, 	 706, 	 704, 	 701, 	 698, 	 696, 	 693, 	 691, 	 688, 	 685, 	 683, 	 680, 	 677, 	675, 	672, 	670, 	667, 	664, 	662, 	659, 	657, 	654, 	651, 	649, 	646, 	644, 	641, 	639, 	636, 	633, 	631, 	628, 	626, 	623, 	621, 	618, 	616, 	613, 	611, 	608, 	606, 	603, 	601, 	598, 	596, 	593, 	591, 	588, 	586, 	583, 	581, 	578, 	576, 	573, 	571, 	569, 	566, 	564, 	561, 	559, 	556, 	554, 	552, 	549, 	547, 	544, 	542, 	540, 	537, 	535, 	533, 	530, 	528, 	525, 	523, 	521, 	518, 	516, 	514, 	511, 	509, 	507, 	504, 	502, 	500, 	497, 	495, 	493, 	491, 	488, 	486, 	484, 	481, 	479, 	477, 	475, 	472, 	470, 	468, 	466, 	463, 	461, 	459, 	457, 	455, 	452, 	450, 	448, 	446, 	444, 	441, 	439, 	437, 	435, 	433, 	430, 	428, 	426, 	424, 	422, 	420, 	418, 	415, 	413, 	411, 	409, 	407, 	405, 	403, 	401, 	399, 	396, 	394, 	392, 	390, 	388, 	386, 	384, 	382, 	380, 	378, 	376, 	374, 	372, 	370, 	368, 	366, 	364, 	362, 	360, 	358, 	356, 	354, 	352, 	350, 	348, 	346, 	344, 	342, 	340, 	338, 	336, 	334, 	332, 	330, 	328, 	326, 	325, 	323, 	321, 	319, 	317, 	315, 	313, 	311, 	309, 	308, 	306, 	304, 	302, 	300, 	298, 	297, 	295, 	293, 	291, 	289, 	287, 	286, 	284, 	282, 	280, 	279, 	277, 	275, 	273, 	271, 	270, 	268, 	266, 	264, 	263, 	261, 	259, 	258, 	256, 	254, 	252, 	251, 	249, 	247, 	246, 	244, 	242, 	241, 	239, 	237, 	236, 	234, 	232, 	231, 	229, 	228, 	226, 	224, 	223, 	221, 	220, 	218, 	216, 	215, 	213, 	212, 	210, 
 209, 	 207, 	 205, 	 204, 	 202, 	 201, 	 199, 	 198, 	 196, 	 195, 	 193, 	 192, 	 190, 	 189, 	 187, 	 186, 	 184, 	 183, 	 182, 	 180, 	 179, 	 177, 	 176, 	 174, 	 173, 	 171, 	 170, 	 169,  	 167, 	 166, 	 164, 	 163, 	 162, 	 160, 	 159, 	158, 	156, 	155, 	154, 	152, 	151, 	150, 	148, 	147, 	146, 	144, 	143, 	142, 	140, 	139, 	138, 	137, 	135, 	134, 	133, 	132, 	130, 	129, 	128, 	127, 	125, 	124, 	123, 	122, 	121, 	119, 	118, 	117, 	116, 	115, 	114, 	112, 	111, 	110, 	109, 	108, 	107, 	106, 	104, 	103, 	102, 	101, 	100, 	99, 	98, 	97, 	96, 	95, 	94, 	93, 	92, 	90, 	89, 	88, 	87, 	86, 	85, 	84, 	83, 	82, 	81, 	80, 	79, 	78, 	77, 	77, 	76, 	75, 	74, 	73, 	72, 	71, 	70, 	69, 	68, 	67, 	66, 	65, 	65, 	64, 	63, 	62, 	61, 	60, 	59, 	59, 	58, 	57, 	56, 	55, 	54, 	54, 	53, 	52, 	51, 	50, 	50, 	49, 	48, 	47, 	47, 	46, 	45, 	44, 	44, 	43, 	42, 	42, 	41, 	40, 	39, 	39, 	38, 	37, 	37, 	36, 	35, 	35, 	34, 	33, 	33, 	32, 	32, 	31, 	30, 	30, 	29, 	29, 	28, 	27, 	27, 	26, 	26, 	25, 	25, 	24, 	24, 	23, 	22, 	22, 	21, 	21, 	20, 	20, 	19, 	19, 	19, 	18, 	18, 	17, 	17, 	16, 	16, 	15, 	15, 	14, 	14, 	14, 	13, 	13, 	12, 	12, 	12, 	11, 	11, 	11, 	10, 	10, 	10, 	9, 	9, 	9, 	8, 	8, 	8, 	7, 	7, 	7, 	6, 	6, 	6, 	6, 	5, 	5, 	5, 	5, 	4, 	4, 	4, 	4, 	4, 	3, 	3, 	3, 	3, 	3, 	2, 	2, 	2, 	2, 	2, 	2, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	0, 	0, 	0, 	0, 
   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   1, 	   1, 	   1, 	   1, 	   1, 	   1, 	   1, 	   1, 	   1, 	   1, 	   2, 	   2, 	   2, 	   2, 	2, 	2, 	3, 	3, 	3, 	3, 	3, 	4, 	4, 	4, 	4, 	4, 	5, 	5, 	5, 	5, 	6, 	6, 	6, 	6, 	7, 	7, 	7, 	8, 	8, 	8, 	9, 	9, 	9, 	10, 	10, 	10, 	11, 	11, 	11, 	12, 	12, 	12, 	13, 	13, 	14, 	14, 	14, 	15, 	15, 	16, 	16, 	17, 	17, 	18, 	18, 	19, 	19, 	19, 	20, 	20, 	21, 	21, 	22, 	22, 	23, 	24, 	24, 	25, 	25, 	26, 	26, 	27, 	27, 	28, 	29, 	29, 	30, 	30, 	31, 	32, 	32, 	33, 	33, 	34, 	35, 	35, 	36, 	37, 	37, 	38, 	39, 	39, 	40, 	41, 	42, 	42, 	43, 	44, 	44, 	45, 	46, 	47, 	47, 	48, 	49, 	50, 	50, 	51, 	52, 	53, 	54, 	54, 	55, 	56, 	57, 	58, 	59, 	59, 	60, 	61, 	62, 	63, 	64, 	65, 	65, 	66, 	67, 	68, 	69, 	70, 	71, 	72, 	73, 	74, 	75, 	76, 	77, 	77, 	78, 	79, 	80, 	81, 	82, 	83, 	84, 	85, 	86, 	87, 	88, 	89, 	90, 	92, 	93, 	94, 	95, 	96, 	97, 	98, 	99, 	100, 	101, 	102, 	103, 	104, 	106, 	107, 	108, 	109, 	110, 	111, 	112, 	114, 	115, 	116, 	117, 	118, 	119, 	121, 	122, 	123, 	124, 	125, 	127, 	128, 	129, 	130, 	132, 	133, 	134, 	135, 	137, 	138, 	139, 	140, 	142, 	143, 	144, 	146, 	147, 	148, 	150, 	151, 	152, 	154, 	155, 	156, 	158, 	159, 	160, 	162, 	163, 	164, 	166, 	167, 	169, 	170, 	171, 	173, 	174, 	176, 	177, 	179, 	180, 	182, 	183, 
 184, 	 186, 	 187, 	 189, 	 190, 	 192, 	 193, 	 195, 	 196, 	 198, 	 199, 	 201, 	 202, 	 204, 	 205, 	 207, 	 209, 	 210, 	 212, 	 213, 	 215, 	 216, 	 218, 	 220, 	 221, 	 223, 	 224, 	 226, 	 228, 	 229, 	 231, 	 232, 	 234, 	 236, 	237, 	239, 	241, 	242, 	244, 	246, 	247, 	249, 	251, 	252, 	254, 	256, 	258, 	259, 	261, 	263, 	264, 	266, 	268, 	270, 	271, 	273, 	275, 	277, 	279, 	280, 	282, 	284, 	286, 	287, 	289, 	291, 	293, 	295, 	297, 	298, 	300, 	302, 	304, 	306, 	308, 	309, 	311, 	313, 	315, 	317, 	319, 	321, 	323, 	325, 	326, 	328, 	330, 	332, 	334, 	336, 	338, 	340, 	342, 	344, 	346, 	348, 	350, 	352, 	354, 	356, 	358, 	360, 	362, 	364, 	366, 	368, 	370, 	372, 	374, 	376, 	378, 	380, 	382, 	384, 	386, 	388, 	390, 	392, 	394, 	396, 	399, 	401, 	403, 	405, 	407, 	409, 	411, 	413, 	415, 	418, 	420, 	422, 	424, 	426, 	428, 	430, 	433, 	435, 	437, 	439, 	441, 	444, 	446, 	448, 	450, 	452, 	455, 	457, 	459, 	461, 	463, 	466, 	468, 	470, 	472, 	475, 	477, 	479, 	481, 	484, 	486, 	488, 	491, 	493, 	495, 	497, 	500, 	502, 	504, 	507, 	509, 	511, 	514, 	516, 	518, 	521, 	523, 	525, 	528, 	530, 	533, 	535, 	537, 	540, 	542, 	544, 	547, 	549, 	552, 	554, 	556, 	559, 	561, 	564, 	566, 	569, 	571, 	573, 	576, 	578, 	581, 	583, 	586, 	588, 	591, 	593, 	596, 	598, 	601, 	603, 	606, 	608, 	611, 	613, 	616, 	618, 	621, 	623, 	626, 	628, 	631, 	633, 	636, 	639, 	641, 	644, 	646, 	649, 	651, 	654, 	657, 	659, 	662, 	664, 	667, 	670, 	672, 	675, 	677, 	680, 	683, 	685, 	688, 	691, 	693, 	696, 	698, 	701, 	704, 	706, 	709, 	712, 	714, 	717, 	720, 	722, 
 725, 	 728, 	 731, 	 733, 	 736, 	 739, 	 741, 	 744, 	 747, 	 750, 	 752, 	 755, 	 758, 	 760, 	 763, 	 766, 	 769, 	 771, 	 774, 	 777, 	 780, 	 782, 	 785, 	 788, 	 791, 	 794, 	 796, 	 799, 	 802, 	 805, 	808, 	810, 	813, 	816, 	819, 	822, 	824, 	827, 	830, 	833, 	836, 	839, 	841, 	844, 	847, 	850, 	853, 	856, 	859, 	861, 	864, 	867, 	870, 	873, 	876, 	879, 	882, 	885, 	887, 	890, 	893, 	896, 	899, 	902, 	905, 	908, 	911, 	914, 	917, 	920, 	922, 	925, 	928, 	931, 	934, 	937, 	940, 	943, 	946, 	949, 	952, 	955, 	958, 	961, 	964, 	967, 	970, 	973, 	976, 	979, 	982, 	985, 	988, 	991, 	994, 	997, 	1000, 	1003, 	1006, 	1009, 	1012, 	1015, 	1018, 	1021, 	1024, 	1027, 	1030, 	1033, 	1036, 	1040, 	1043, 	1046, 	1049, 	1052, 	1055, 	1058, 	1061, 	1064, 	1067, 	1070, 	1073, 	1077, 	1080, 	1083, 	1086, 	1089, 	1092, 	1095, 	1098, 	1101, 	1104, 	1108, 	1111, 	1114, 	1117, 	1120, 	1123, 	1126, 	1130, 	1133, 	1136, 	1139, 	1142, 	1145, 	1148, 	1152, 	1155, 	1158, 	1161, 	1164, 	1167, 	1171, 	1174, 	1177, 	1180, 	1183, 	1187, 	1190, 	1193, 	1196, 	1199, 	1203, 	1206, 	1209, 	1212, 	1215, 	1219, 	1222, 	1225, 	1228, 	1231, 	1235, 	1238, 	1241, 	1244, 	1248, 	1251, 	1254, 	1257, 	1261, 	1264, 	1267, 	1270, 	1273, 	1277, 	1280, 	1283, 	1287, 	1290, 	1293, 	1296, 	1300, 	1303, 	1306, 	1309, 	1313, 	1316, 	1319, 	1323, 	1326, 	1329, 	1332, 	1336, 	1339, 	1342, 	1346, 	1349, 	1352, 	1355, 	1359, 	1362, 	1365, 	1369, 	1372, 	1375, 	1379, 	1382, 	1385, 	1389, 	1392, 	1395, 	1399, 	1402, 	1405, 	1409, 	1412, 	1415, 	1419, 	1422, 	1425, 	1429, 	1432, 	1435, 	1439, 	1442, 	1445, 	1449, 	1452, 	1455, 	1459, 	1462, 	1466, 	1469, 	1472, 	1476, 	1479, 	1482, 	1486, 	1489, 	1492, 	1496, 	1499, 	1503, 	1506, 	1509, 	1513, 
1516, 	1520, 	1523, 	1526, 	1530, 	1533, 	1537, 	1540, 	1543, 	1547, 	1550, 	1553, 	1557, 	1560, 	1564, 	1567, 	1571, 	1574, 	1577, 	1581, 	1584, 	1588, 	1591, 	1594, 	1598, 	1601, 	1605, 	1608, 	1612, 	1615, 	1618, 	1622, 	1625, 	1629, 	1632, 	1636, 	1639, 	1642, 	1646, 	1649, 	1653, 	1656, 	1660, 	1663, 	1666, 	1670, 	1673, 	1677, 	1680, 	1684, 	1687, 	1691, 	1694, 	1697, 	1701, 	1704, 	1708, 	1711, 	1715, 	1718, 	1722, 	1725, 	1729, 	1732, 	1735, 	1739, 	1742, 	1746, 	1749, 	1753, 	1756, 	1760, 	1763, 	1767, 	1770, 	1774, 	1777, 	1781, 	1784, 	1787, 	1791, 	1794, 	1798, 	1801, 	1805, 	1808, 	1812, 	1815, 	1819, 	1822, 	1826, 	1829, 	1833, 	1836, 	1840, 	1843, 	1847, 	1850, 	1854, 	1857, 	1860, 	1864, 	1867, 	1871, 	1874, 	1878, 	1881, 	1885, 	1888, 	1892, 	1895, 	1899, 	1902, 	1906, 	1909, 	1913, 	1916, 	1920, 	1923, 	1927, 	1930, 	1934, 	1937, 	1941, 	1944, 	1948, 	1951, 	1955, 	1958, 	1962, 	1965, 	1969, 	1972, 	1976, 	1979, 	1983, 	1986, 	1990, 	1993, 	1997, 	2000, 	2003, 	2007, 	2010, 	2014, 	2017, 	2021, 	2024, 	2028, 	2031, 	2035, 	2038, 	2042, 	2045, 	2049, 	2052, 	2056, 	2059, 	2063, 	2066, 	2070, 	2073, 	2077, 	2080, 	2084, 	2087, 	2091, 	2094, 	2098, 	2101, 	2105, 	2108, 	2112, 	2115, 	2119, 	2122, 	2126, 	2129, 	2133, 	2136, 	2140, 	2143, 	2146, 	2150, 	2153, 	2157, 	2160, 	2164, 	2167, 	2171, 	2174, 	2178, 	2181, 	2185, 	2188, 	2192, 	2195, 	2199, 	2202, 	2206, 	2209, 	2213, 	2216, 	2219, 	2223, 	2226, 	2230, 	2233, 	2237, 	2240, 	2244, 	2247, 	2251, 	2254, 	2258, 	2261, 	2265, 	2268, 	2271, 	2275, 	2278, 	2282, 	2285, 	2289, 	2292, 	2296, 	2299, 	2303, 	2306, 	2309, 	2313, 	2316, 	2320, 	2323, 	2327, 	2330, 	2334, 	2337, 	2340, 	2344, 	2347, 	2351, 	2354, 	2358, 	2361, 	2364, 	2368, 	2371, 	2375, 	2378, 	2382, 	2385, 	2388, 	2392, 	2395, 	2399, 
2402, 	2406, 	2409, 	2412, 	2416, 	2419, 	2423, 	2426, 	2429, 	2433, 	2436, 	2440, 	2443, 	2447, 	2450, 	2453, 	2457, 	2460, 	2463, 	2467, 	2470, 	2474, 	2477, 	2480, 	2484, 	2487, 	2491, 	2494, 	2497, 	2501, 	2504, 	2508, 	2511, 	2514, 	2518, 	2521, 	2524, 	2528, 	2531, 	2534, 	2538, 	2541, 	2545, 	2548, 	2551, 	2555, 	2558, 	2561, 	2565, 	2568, 	2571, 	2575, 	2578, 	2581, 	2585, 	2588, 	2591, 	2595, 	2598, 	2601, 	2605, 	2608, 	2611, 	2615, 	2618, 	2621, 	2625, 	2628, 	2631, 	2635, 	2638, 	2641, 	2645, 	2648, 	2651, 	2654, 	2658, 	2661, 	2664, 	2668, 	2671, 	2674, 	2677, 	2681, 	2684, 	2687, 	2691, 	2694, 	2697, 	2700, 	2704, 	2707, 	2710, 	2713, 	2717, 	2720, 	2723, 	2727, 	2730, 	2733, 	2736, 	2739, 	2743, 	2746, 	2749, 	2752, 	2756, 	2759, 	2762, 	2765, 	2769, 	2772, 	2775, 	2778, 	2781, 	2785, 	2788, 	2791, 	2794, 	2797, 	2801, 	2804, 	2807, 	2810, 	2813, 	2817, 	2820, 	2823, 	2826, 	2829, 	2833, 	2836, 	2839, 	2842, 	2845, 	2848, 	2852, 	2855, 	2858, 	2861, 	2864, 	2867, 	2870, 	2874, 	2877, 	2880, 	2883, 	2886, 	2889, 	2892, 	2896, 	2899, 	2902, 	2905, 	2908, 	2911, 	2914, 	2917, 	2920, 	2923, 	2927, 	2930, 	2933, 	2936, 	2939, 	2942, 	2945, 	2948, 	2951, 	2954, 	2957, 	2960, 	2964, 	2967, 	2970, 	2973, 	2976, 	2979, 	2982, 	2985, 	2988, 	2991, 	2994, 	2997, 	3000, 	3003, 	3006, 	3009, 	3012, 	3015, 	3018, 	3021, 	3024, 	3027, 	3030, 	3033, 	3036, 	3039, 	3042, 	3045, 	3048, 	3051, 	3054, 	3057, 	3060, 	3063, 	3066, 	3069, 	3072, 	3075, 	3078, 	3080, 	3083, 	3086, 	3089, 	3092, 	3095, 	3098, 	3101, 	3104, 	3107, 	3110, 	3113, 	3115, 	3118, 	3121, 	3124, 	3127, 	3130, 	3133, 	3136, 	3139, 	3141, 	3144, 	3147, 	3150, 	3153, 	3156, 	3159, 	3161, 	3164, 	3167, 	3170, 	3173, 	3176, 	3178, 	3181, 	3184, 	3187, 	3190, 	3192, 	3195, 	3198, 	3201, 	3204, 	3206, 
3209, 	3212, 	3215, 	3218, 	3220, 	3223, 	3226, 	3229, 	3231, 	3234, 	3237, 	3240, 	3242, 	3245, 	3248, 	3250, 	3253, 	3256, 	3259, 	3261, 	3264, 	3267, 	3269, 	3272, 	3275, 	3278, 	3280, 	3283, 	3286, 	3288, 	3291, 	3294, 	3296, 	3299, 	3302, 	3304, 	3307, 	3309, 	3312, 	3315, 	3317, 	3320, 	3323, 	3325, 	3328, 	3330, 	3333, 	3336, 	3338, 	3341, 	3343, 	3346, 	3349, 	3351, 	3354, 	3356, 	3359, 	3361, 	3364, 	3367, 	3369, 	3372, 	3374, 	3377, 	3379, 	3382, 	3384, 	3387, 	3389, 	3392, 	3394, 	3397, 	3399, 	3402, 	3404, 	3407, 	3409, 	3412, 	3414, 	3417, 	3419, 	3422, 	3424, 	3427, 	3429, 	3431, 	3434, 	3436, 	3439, 	3441, 	3444, 	3446, 	3448, 	3451, 	3453, 	3456, 	3458, 	3460, 	3463, 	3465, 	3467, 	3470, 	3472, 	3475, 	3477, 	3479, 	3482, 	3484, 	3486, 	3489, 	3491, 	3493, 	3496, 	3498, 	3500, 	3503, 	3505, 	3507, 	3509, 	3512, 	3514, 	3516, 	3519, 	3521, 	3523, 	3525, 	3528, 	3530, 	3532, 	3534, 	3537, 	3539, 	3541, 	3543, 	3545, 	3548, 	3550, 	3552, 	3554, 	3556, 	3559, 	3561, 	3563, 	3565, 	3567, 	3570, 	3572, 	3574, 	3576, 	3578, 	3580, 	3582, 	3585, 	3587, 	3589, 	3591, 	3593, 	3595, 	3597, 	3599, 	3601, 	3604, 	3606, 	3608, 	3610, 	3612, 	3614, 	3616, 	3618, 	3620, 	3622, 	3624, 	3626, 	3628, 	3630, 	3632, 	3634, 	3636, 	3638, 	3640, 	3642, 	3644, 	3646, 	3648, 	3650, 	3652, 	3654, 	3656, 	3658, 	3660, 	3662, 	3664, 	3666, 	3668, 	3670, 	3672, 	3674, 	3675, 	3677, 	3679, 	3681, 	3683, 	3685, 	3687, 	3689, 	3691, 	3692, 	3694, 	3696, 	3698, 	3700, 	3702, 	3703, 	3705, 	3707, 	3709, 	3711, 	3713, 	3714, 	3716, 	3718, 	3720, 	3721, 	3723, 	3725, 	3727, 	3729, 	3730, 	3732, 	3734, 	3736, 	3737, 	3739, 	3741, 	3742, 	3744, 	3746, 	3748, 	3749, 	3751, 	3753, 	3754, 	3756, 	3758, 	3759, 	3761, 	3763, 	3764, 	3766, 	3768, 	3769, 	3771, 	3772, 	3774, 	3776, 	3777, 
3779, 	3780, 	3782, 	3784, 	3785, 	3787, 	3788, 	3790, 	3791, 	3793, 	3795, 	3796, 	3798, 	3799, 	3801, 	3802, 	3804, 	3805, 	3807, 	3808, 	3810, 	3811, 	3813, 	3814, 	3816, 	3817, 	3818, 	3820, 	3821, 	3823, 	3824, 	3826, 	3827, 	3829, 	3830, 	3831, 	3833, 	3834, 	3836, 	3837, 	3838, 	3840, 	3841, 	3842, 	3844, 	3845, 	3846, 	3848, 	3849, 	3850, 	3852, 	3853, 	3854, 	3856, 	3857, 	3858, 	3860, 	3861, 	3862, 	3863, 	3865, 	3866, 	3867, 	3868, 	3870, 	3871, 	3872, 	3873, 	3875, 	3876, 	3877, 	3878, 	3879, 	3881, 	3882, 	3883, 	3884, 	3885, 	3886, 	3888, 	3889, 	3890, 	3891, 	3892, 	3893, 	3894, 	3896, 	3897, 	3898, 	3899, 	3900, 	3901, 	3902, 	3903, 	3904, 	3905, 	3906, 	3907, 	3908, 	3910, 	3911, 	3912, 	3913, 	3914, 	3915, 	3916, 	3917, 	3918, 	3919, 	3920, 	3921, 	3922, 	3923, 	3923, 	3924, 	3925, 	3926, 	3927, 	3928, 	3929, 	3930, 	3931, 	3932, 	3933, 	3934, 	3935, 	3935, 	3936, 	3937, 	3938, 	3939, 	3940, 	3941, 	3941, 	3942, 	3943, 	3944, 	3945, 	3946, 	3946, 	3947, 	3948, 	3949, 	3950, 	3950, 	3951, 	3952, 	3953, 	3953, 	3954, 	3955, 	3956, 	3956, 	3957, 	3958, 	3958, 	3959, 	3960, 	3961, 	3961, 	3962, 	3963, 	3963, 	3964, 	3965, 	3965, 	3966, 	3967, 	3967, 	3968, 	3968, 	3969, 	3970, 	3970, 	3971, 	3971, 	3972, 	3973, 	3973, 	3974, 	3974, 	3975, 	3975, 	3976, 	3976, 	3977, 	3978, 	3978, 	3979, 	3979, 	3980, 	3980, 	3981, 	3981, 	3981, 	3982, 	3982, 	3983, 	3983, 	3984, 	3984, 	3985, 	3985, 	3986, 	3986, 	3986, 	3987, 	3987, 	3988, 	3988, 	3988, 	3989, 	3989, 	3989, 	3990, 	3990, 	3990, 	3991, 	3991, 	3991, 	3992, 	3992, 	3992, 	3993, 	3993, 	3993, 	3994, 	3994, 	3994, 	3994, 	3995, 	3995, 	3995, 	3995, 	3996, 	3996, 	3996, 	3996, 	3996, 	3997, 	3997, 	3997, 	3997, 	3997, 	3998, 	3998, 	3998, 	3998, 	3998, 	3998, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 
3999, 	3999, 	3999, 	3999, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	4000, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3999, 	3998, 	3998, 	3998, 	3998, 	3998, 	3998, 	3997, 	3997, 	3997, 	3997, 	3997, 	3996, 	3996, 	3996, 	3996, 	3996, 	3995, 	3995, 	3995, 	3995, 	3994, 	3994, 	3994, 	3994, 	3993, 	3993, 	3993, 	3992, 	3992, 	3992, 	3991, 	3991, 	3991, 	3990, 	3990, 	3990, 	3989, 	3989, 	3989, 	3988, 	3988, 	3988, 	3987, 	3987, 	3986, 	3986, 	3986, 	3985, 	3985, 	3984, 	3984, 	3983, 	3983, 	3982, 	3982, 	3981, 	3981, 	3981, 	3980, 	3980, 	3979, 	3979, 	3978, 	3978, 	3977, 	3976, 	3976, 	3975, 	3975, 	3974, 	3974, 	3973, 	3973, 	3972, 	3971, 	3971, 	3970, 	3970, 	3969, 	3968, 	3968, 	3967, 	3967, 	3966, 	3965, 	3965, 	3964, 	3963, 	3963, 	3962, 	3961, 	3961, 	3960, 	3959, 	3958, 	3958, 	3957, 	3956, 	3956, 	3955, 	3954, 	3953, 	3953, 	3952, 	3951, 	3950, 	3950, 	3949, 	3948, 	3947, 	3946, 	3946, 	3945, 	3944, 	3943, 	3942, 	3941, 	3941, 	3940, 	3939, 	3938, 	3937, 	3936, 	3935, 	3935, 	3934, 	3933, 	3932, 	3931, 	3930, 	3929, 	3928, 	3927, 	3926, 	3925, 	3924, 	3923, 	3923, 	3922, 	3921, 	3920, 	3919, 	3918, 	3917, 	3916, 	3915, 	3914, 	3913, 	3912, 	3911, 	3910, 	3908, 	3907, 	3906, 	3905, 	3904, 	3903, 	3902, 	3901, 	3900, 	3899, 	3898, 	3897, 	3896, 	3894, 	3893, 	3892, 	3891, 	3890, 	3889, 	3888, 	3886, 	3885, 	3884, 	3883, 	3882, 	3881, 	3879, 	3878, 	3877, 	3876, 	3875, 	3873, 	3872, 	3871, 	3870, 	3868, 	3867, 	3866, 	3865, 	3863, 	3862, 	3861, 	3860, 	3858, 	3857, 	3856, 	3854, 	3853, 	3852, 	3850, 	3849, 	3848, 	3846, 	3845, 	3844, 	3842, 	3841, 	3840, 	3838, 	3837, 	3836, 	3834, 	3833, 	3831, 	3830, 	3829, 
3827, 	3826, 	3824, 	3823, 	3821, 	3820, 	3818, 	3817, 	3816, 	3814, 	3813, 	3811, 	3810, 	3808, 	3807, 	3805, 	3804, 	3802, 	3801, 	3799, 	3798, 	3796, 	3795, 	3793, 	3791, 	3790, 	3788, 	3787, 	3785, 	3784, 	3782, 	3780, 	3779, 	3777, 	3776, 	3774, 	3772, 	3771, 	3769, 	3768, 	3766, 	3764, 	3763, 	3761, 	3759, 	3758, 	3756, 	3754, 	3753, 	3751, 	3749, 	3748, 	3746, 	3744, 	3742, 	3741, 	3739, 	3737, 	3736, 	3734, 	3732, 	3730, 	3729, 	3727, 	3725, 	3723, 	3721, 	3720, 	3718, 	3716, 	3714, 	3713, 	3711, 	3709, 	3707, 	3705, 	3703, 	3702, 	3700, 	3698, 	3696, 	3694, 	3692, 	3691, 	3689, 	3687, 	3685, 	3683, 	3681, 	3679, 	3677, 	3675, 	3674, 	3672, 	3670, 	3668, 	3666, 	3664, 	3662, 	3660, 	3658, 	3656, 	3654, 	3652, 	3650, 	3648, 	3646, 	3644, 	3642, 	3640, 	3638, 	3636, 	3634, 	3632, 	3630, 	3628, 	3626, 	3624, 	3622, 	3620, 	3618, 	3616, 	3614, 	3612, 	3610, 	3608, 	3606, 	3604, 	3601, 	3599, 	3597, 	3595, 	3593, 	3591, 	3589, 	3587, 	3585, 	3582, 	3580, 	3578, 	3576, 	3574, 	3572, 	3570, 	3567, 	3565, 	3563, 	3561, 	3559, 	3556, 	3554, 	3552, 	3550, 	3548, 	3545, 	3543, 	3541, 	3539, 	3537, 	3534, 	3532, 	3530, 	3528, 	3525, 	3523, 	3521, 	3519, 	3516, 	3514, 	3512, 	3509, 	3507, 	3505, 	3503, 	3500, 	3498, 	3496, 	3493, 	3491, 	3489, 	3486, 	3484, 	3482, 	3479, 	3477, 	3475, 	3472, 	3470, 	3467, 	3465, 	3463, 	3460, 	3458, 	3456, 	3453, 	3451, 	3448, 	3446, 	3444, 	3441, 	3439, 	3436, 	3434, 	3431, 	3429, 	3427, 	3424, 	3422, 	3419, 	3417, 	3414, 	3412, 	3409, 	3407, 	3404, 	3402, 	3399, 	3397, 	3394, 	3392, 	3389, 	3387, 	3384, 	3382, 	3379, 	3377, 	3374, 	3372, 	3369, 	3367, 	3364, 	3361, 	3359, 	3356, 	3354, 	3351, 	3349, 	3346, 	3343, 	3341, 	3338, 	3336, 	3333, 	3330, 	3328, 	3325, 	3323, 	3320, 	3317, 	3315, 	3312, 	3309, 	3307, 	3304, 	3302, 	3299, 
3296, 	3294, 	3291, 	3288, 	3286, 	3283, 	3280, 	3278, 	3275, 	3272, 	3269, 	3267, 	3264, 	3261, 	3259, 	3256, 	3253, 	3250, 	3248, 	3245, 	3242, 	3240, 	3237, 	3234, 	3231, 	3229, 	3226, 	3223, 	3220, 	3218, 	3215, 	3212, 	3209, 	3206, 	3204, 	3201, 	3198, 	3195, 	3192, 	3190, 	3187, 	3184, 	3181, 	3178, 	3176, 	3173, 	3170, 	3167, 	3164, 	3161, 	3159, 	3156, 	3153, 	3150, 	3147, 	3144, 	3141, 	3139, 	3136, 	3133, 	3130, 	3127, 	3124, 	3121, 	3118, 	3115, 	3113, 	3110, 	3107, 	3104, 	3101, 	3098, 	3095, 	3092, 	3089, 	3086, 	3083, 	3080, 	3078, 	3075, 	3072, 	3069, 	3066, 	3063, 	3060, 	3057, 	3054, 	3051, 	3048, 	3045, 	3042, 	3039, 	3036, 	3033, 	3030, 	3027, 	3024, 	3021, 	3018, 	3015, 	3012, 	3009, 	3006, 	3003, 	3000, 	2997, 	2994, 	2991, 	2988, 	2985, 	2982, 	2979, 	2976, 	2973, 	2970, 	2967, 	2964, 	2960, 	2957, 	2954, 	2951, 	2948, 	2945, 	2942, 	2939, 	2936, 	2933, 	2930, 	2927, 	2923, 	2920, 	2917, 	2914, 	2911, 	2908, 	2905, 	2902, 	2899, 	2896, 	2892, 	2889, 	2886, 	2883, 	2880, 	2877, 	2874, 	2870, 	2867, 	2864, 	2861, 	2858, 	2855, 	2852, 	2848, 	2845, 	2842, 	2839, 	2836, 	2833, 	2829, 	2826, 	2823, 	2820, 	2817, 	2813, 	2810, 	2807, 	2804, 	2801, 	2797, 	2794, 	2791, 	2788, 	2785, 	2781, 	2778, 	2775, 	2772, 	2769, 	2765, 	2762, 	2759, 	2756, 	2752, 	2749, 	2746, 	2743, 	2739, 	2736, 	2733, 	2730, 	2727, 	2723, 	2720, 	2717, 	2713, 	2710, 	2707, 	2704, 	2700, 	2697, 	2694, 	2691, 	2687, 	2684, 	2681, 	2677, 	2674, 	2671, 	2668, 	2664, 	2661, 	2658, 	2654, 	2651, 	2648, 	2645, 	2641, 	2638, 	2635, 	2631, 	2628, 	2625, 	2621, 	2618, 	2615, 	2611, 	2608, 	2605, 	2601, 	2598, 	2595, 	2591, 	2588, 	2585, 	2581, 	2578, 	2575, 	2571, 	2568, 	2565, 	2561, 	2558, 	2555, 	2551, 	2548, 	2545, 	2541, 	2538, 	2534, 	2531, 	2528, 	2524, 	2521, 	2518, 	2514, 
2511, 	2508, 	2504, 	2501, 	2497, 	2494, 	2491, 	2487, 	2484, 	2480, 	2477, 	2474, 	2470, 	2467, 	2463, 	2460, 	2457, 	2453, 	2450, 	2447, 	2443, 	2440, 	2436, 	2433, 	2429, 	2426, 	2423, 	2419, 	2416, 	2412, 	2409, 	2406, 	2402, 	2399, 	2395, 	2392, 	2388, 	2385, 	2382, 	2378, 	2375, 	2371, 	2368, 	2364, 	2361, 	2358, 	2354, 	2351, 	2347, 	2344, 	2340, 	2337, 	2334, 	2330, 	2327, 	2323, 	2320, 	2316, 	2313, 	2309, 	2306, 	2303, 	2299, 	2296, 	2292, 	2289, 	2285, 	2282, 	2278, 	2275, 	2271, 	2268, 	2265, 	2261, 	2258, 	2254, 	2251, 	2247, 	2244, 	2240, 	2237, 	2233, 	2230, 	2226, 	2223, 	2219, 	2216, 	2213, 	2209, 	2206, 	2202, 	2199, 	2195, 	2192, 	2188, 	2185, 	2181, 	2178, 	2174, 	2171, 	2167, 	2164, 	2160, 	2157, 	2153, 	2150, 	2146, 	2143, 	2140, 	2136, 	2133, 	2129, 	2126, 	2122, 	2119, 	2115, 	2112, 	2108, 	2105, 	2101, 	2098, 	2094, 	2091, 	2087, 	2084, 	2080, 	2077, 	2073, 	2070, 	2066, 	2063, 	2059, 	2056, 	2052, 	2049, 	2045, 	2042, 	2038, 	2035, 	2031, 	2028, 	2024, 	2021, 	2017, 	2014, 	2010, 	2007, 	2003, 	2000, 	1997, 	1993, 	1990, 	1986, 	1983, 	1979, 	1976, 	1972, 	1969, 	1965, 	1962, 	1958, 	1955, 	1951, 	1948, 	1944, 	1941, 	1937, 	1934, 	1930, 	1927, 	1923, 	1920, 	1916, 	1913, 	1909, 	1906, 	1902, 	1899, 	1895, 	1892, 	1888, 	1885, 	1881, 	1878, 	1874, 	1871, 	1867, 	1864, 	1860, 	1857, 	1854, 	1850, 	1847, 	1843, 	1840, 	1836, 	1833, 	1829, 	1826, 	1822, 	1819, 	1815, 	1812, 	1808, 	1805, 	1801, 	1798, 	1794, 	1791, 	1787, 	1784, 	1781, 	1777, 	1774, 	1770, 	1767, 	1763, 	1760, 	1756, 	1753, 	1749, 	1746, 	1742, 	1739, 	1735, 	1732, 	1729, 	1725, 	1722, 	1718, 	1715, 	1711, 	1708, 	1704, 	1701, 	1697, 	1694, 	1691, 	1687, 	1684, 	1680, 	1677, 	1673, 	1670, 	1666, 	1663, 	1660, 	1656, 	1653, 	1649, 	1646, 	1642, 	1639, 	1636, 	1632, 	1629, 
1625, 	1622, 	1618, 	1615, 	1612, 	1608, 	1605, 	1601, 	1598, 	1594, 	1591, 	1588, 	1584, 	1581, 	1577, 	1574, 	1571, 	1567, 	1564, 	1560, 	1557, 	1553, 	1550, 	1547, 	1543, 	1540, 	1537, 	1533, 	1530, 	1526, 	1523, 	1520, 	1516, 	1513, 	1509, 	1506, 	1503, 	1499, 	1496, 	1492, 	1489, 	1486, 	1482, 	1479, 	1476, 	1472, 	1469, 	1466, 	1462, 	1459, 	1455, 	1452, 	1449, 	1445, 	1442, 	1439, 	1435, 	1432, 	1429, 	1425, 	1422, 	1419, 	1415, 	1412, 	1409, 	1405, 	1402, 	1399, 	1395, 	1392, 	1389, 	1385, 	1382, 	1379, 	1375, 	1372, 	1369, 	1365, 	1362, 	1359, 	1355, 	1352, 	1349, 	1346, 	1342, 	1339, 	1336, 	1332, 	1329, 	1326, 	1323, 	1319, 	1316, 	1313, 	1309, 	1306, 	1303, 	1300, 	1296, 	1293, 	1290, 	1287, 	1283, 	1280, 	1277, 	1273, 	1270, 	1267, 	1264, 	1261, 	1257, 	1254, 	1251, 	1248, 	1244, 	1241, 	1238, 	1235, 	1231, 	1228, 	1225, 	1222, 	1219, 	1215, 	1212, 	1209, 	1206, 	1203, 	1199, 	1196, 	1193, 	1190, 	1187, 	1183, 	1180, 	1177, 	1174, 	1171, 	1167, 	1164, 	1161, 	1158, 	1155, 	1152, 	1148, 	1145, 	1142, 	1139, 	1136, 	1133, 	1130, 	1126, 	1123, 	1120, 	1117, 	1114, 	1111, 	1108, 	1104, 	1101, 	1098, 	1095, 	1092, 	1089, 	1086, 	1083, 	1080, 	1077, 	1073, 	1070, 	1067, 	1064, 	1061, 	1058, 	1055, 	1052, 	1049, 	1046, 	1043, 	1040, 	1036, 	1033, 	1030, 	1027, 	1024, 	1021, 	1018, 	1015, 	1012, 	1009, 	1006, 	1003, 	1000, 	997, 	994, 	991, 	988, 	985, 	982, 	979, 	976, 	973, 	970, 	967, 	964, 	961, 	958, 	955, 	952, 	949, 	946, 	943, 	940, 	937, 	934, 	931, 	928, 	925, 	922, 	920, 	917, 	914, 	911, 	908, 	905, 	902, 	899, 	896, 	893, 	890, 	887, 	885, 	882, 	879, 	876, 	873, 	870, 	867, 	864, 	861, 	859, 	856, 	853, 	850, 	847, 	844, 	841, 	839, 	836, 	833, 	830, 	827, 	824, 	822, 	819, 	816, 
 813, 	 810, 	 808, 	 805,  	 802,  	 799, 	 796, 	 794, 	 791, 	 788, 	 785, 	 782, 	 780, 	 777, 	 774, 	 771, 	 769, 	 766, 	 763, 	 760,  	 758,  	 755, 	 752,  	750,  	747, 	744, 	741, 	739, 	736, 	733, 	731, 	728, 	725, 	722, 	720, 	717, 	714, 	712, 	709, 	706, 	704, 	701, 	698, 	696, 	693, 	691, 	688, 	685, 	683, 	680, 	677, 	675, 	672, 	670, 	667, 	664, 	662, 	659, 	657, 	654, 	651, 	649, 	646, 	644, 	641, 	639, 	636, 	633, 	631, 	628, 	626, 	623, 	621, 	618, 	616, 	613, 	611, 	608, 	606, 	603, 	601, 	598, 	596, 	593, 	591, 	588, 	586, 	583, 	581, 	578, 	576, 	573, 	571, 	569, 	566, 	564, 	561, 	559, 	556, 	554, 	552, 	549, 	547, 	544, 	542, 	540, 	537, 	535, 	533, 	530, 	528, 	525, 	523, 	521, 	518, 	516, 	514, 	511, 	509, 	507, 	504, 	502, 	500, 	497, 	495, 	493, 	491, 	488, 	486, 	484, 	481, 	479, 	477, 	475, 	472, 	470, 	468, 	466, 	463, 	461, 	459, 	457, 	455, 	452, 	450, 	448, 	446, 	444, 	441, 	439, 	437, 	435, 	433, 	430, 	428, 	426, 	424, 	422, 	420, 	418, 	415, 	413, 	411, 	409, 	407, 	405, 	403, 	401, 	399, 	396, 	394, 	392, 	390, 	388, 	386, 	384, 	382, 	380, 	378, 	376, 	374, 	372, 	370, 	368, 	366, 	364, 	362, 	360, 	358, 	356, 	354, 	352, 	350, 	348, 	346, 	344, 	342, 	340, 	338, 	336, 	334, 	332, 	330, 	328, 	326, 	325, 	323, 	321, 	319, 	317, 	315, 	313, 	311, 	309, 	308, 	306, 	304, 	302, 	300, 	298, 	297, 	295, 	293, 	291, 	289, 	287, 	286, 	284, 	282, 	280, 	279, 	277, 	275, 	273, 	271, 	270, 	268, 	266, 	264, 	263, 	261, 	259, 	258, 	256, 	254, 	252, 	251, 	249, 	247, 	246, 	244, 	242, 	241, 	239, 	237, 	236, 
 234, 	 232, 	 231,  	 229, 	 228, 	 226, 	 224, 	 223, 	 221, 	 220, 	 218, 	 216, 	 215, 	 213, 	 212, 	 210, 	 209, 	 207, 	 205, 	 204, 	 202, 	 201, 	 199, 	198, 	196, 	195, 	193, 	192, 	190, 	189, 	187, 	186, 	184, 	183, 	182, 	180, 	179, 	177, 	176, 	174, 	173, 	171, 	170, 	169, 	167, 	166, 	164, 	163, 	162, 	160, 	159, 	158, 	156, 	155, 	154, 	152, 	151, 	150, 	148, 	147, 	146, 	144, 	143, 	142, 	140, 	139, 	138, 	137, 	135, 	134, 	133, 	132, 	130, 	129, 	128, 	127, 	125, 	124, 	123, 	122, 	121, 	119, 	118, 	117, 	116, 	115, 	114, 	112, 	111, 	110, 	109, 	108, 	107, 	106, 	104, 	103, 	102, 	101, 	100, 	99, 	98, 	97, 	96, 	95, 	94, 	93, 	92, 	90, 	89, 	88, 	87, 	86, 	85, 	84, 	83, 	82, 	81, 	80, 	79, 	78, 	77, 	77, 	76, 	75, 	74, 	73, 	72, 	71, 	70, 	69, 	68, 	67, 	66, 	65, 	65, 	64, 	63, 	62, 	61, 	60, 	59, 	59, 	58, 	57, 	56, 	55, 	54, 	54, 	53, 	52, 	51, 	50, 	50, 	49, 	48, 	47, 	47, 	46, 	45, 	44, 	44, 	43, 	42, 	42, 	41, 	40, 	39, 	39, 	38, 	37, 	37, 	36, 	35, 	35, 	34, 	33, 	33, 	32, 	32, 	31, 	30, 	30, 	29, 	29, 	28, 	27, 	27, 	26, 	26, 	25, 	25, 	24, 	24, 	23, 	22, 	22, 	21, 	21, 	20, 	20, 	19, 	19, 	19, 	18, 	18, 	17, 	17, 	16, 	16, 	15, 	15, 	14, 	14, 	14, 	13, 	13, 	12, 	12, 	12, 	11, 	11, 	11, 	10, 	10, 	10, 	9, 	9, 	9, 	8, 	8, 	8, 	7, 	7, 	7, 	6, 	6, 	6, 	6, 	5, 	5, 	5, 	5, 	4, 	4, 	4, 	4, 	4, 	3, 	3, 	3, 	3, 	3, 	2, 	2, 	2, 	2, 
   2, 	   2, 	    1, 	   1, 	   1, 	   1,   	 1, 	   1, 	    1, 	   1, 	   1, 	   1, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	   0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	0, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	1, 	2, 	2, 	2, 	2, 	2, 	2, 	3, 	3, 	3, 	3, 	3, 	4, 	4, 	4, 	4, 	4, 	5, 	5, 	5, 	5, 	6, 	6, 	6, 	6, 	7, 	7, 	7, 	8, 	8, 	8, 	9, 	9, 	9, 	10, 	10, 	10, 	11, 	11, 	11, 	12, 	12, 	12, 	13, 	13, 	14, 	14, 	14, 	15, 	15, 	16, 	16, 	17, 	17, 	18, 	18, 	19, 	19, 	19, 	20, 	20, 	21, 	21, 	22, 	22, 	23, 	24, 	24, 	25, 	25, 	26, 	26, 	27, 	27, 	28, 	29, 	29, 	30, 	30, 	31, 	32, 	32, 	33, 	33, 	34, 	35, 	35, 	36, 	37, 	37, 	38, 	39, 	39, 	40, 	41, 	42, 	42, 	43, 	44, 	44, 	45, 	46, 	47, 	47, 	48, 	49, 	50, 	50, 	51, 	52, 	53, 	54, 	54, 	55, 	56, 	57, 	58, 	59, 	59, 	60, 	61, 	62, 	63, 	64, 	65, 	65, 	66, 	67, 	68, 	69, 	70, 	71, 	72, 	73, 	74, 	75, 	76, 	77, 	77, 	78, 	79, 	80, 	81, 	82, 	83, 	84, 	85, 	86, 	87, 	88, 	89, 	90, 	92, 	93, 	94, 	95, 	96, 	97, 	98, 	99, 	100, 	101, 	102, 	103, 	104, 	106, 	107, 	108, 	109, 	110, 	111, 	112, 	114, 	115, 	116, 	117, 	118, 	119, 	121, 	122, 	123, 	124, 	125, 	127, 	128, 	129, 	130, 	132, 	133, 	134, 	135, 	137, 	138, 	139, 	140, 	142, 	143, 	144, 	146, 	147, 	148, 	150, 	151, 	152, 	154, 	155, 	156, 	158, 	159, 	160, 
 162, 	 163, 	 164, 	 166, 	 167, 	 169, 	 170, 	 171, 	 173, 	 174, 	 176, 	 177, 	 179, 	 180, 	 182, 	 183, 	 184, 	 186, 	 187, 	 189, 	 190, 	192, 	193, 	195, 	196, 	198, 	199, 	201, 	202, 	204, 	205, 	207, 	209, 	210, 	212, 	213, 	215, 	216, 	218, 	220, 	221, 	223, 	224, 	226, 	228, 	229, 	231, 	232, 	234, 	236, 	237, 	239, 	241, 	242, 	244, 	246, 	247, 	249, 	251, 	252, 	254, 	256, 	258, 	259, 	261, 	263, 	264, 	266, 	268, 	270, 	271, 	273, 	275, 	277, 	279, 	280, 	282, 	284, 	286, 	287, 	289, 	291, 	293, 	295, 	297, 	298, 	300, 	302, 	304, 	306, 	308, 	309, 	311, 	313, 	315, 	317, 	319, 	321, 	323, 	325, 	326, 	328, 	330, 	332, 	334, 	336, 	338, 	340, 	342, 	344, 	346, 	348, 	350, 	352, 	354, 	356, 	358, 	360, 	362, 	364, 	366, 	368, 	370, 	372, 	374, 	376, 	378, 	380, 	382, 	384, 	386, 	388, 	390, 	392, 	394, 	396, 	399, 	401, 	403, 	405, 	407, 	409, 	411, 	413, 	415, 	418, 	420, 	422, 	424, 	426, 	428, 	430, 	433, 	435, 	437, 	439, 	441, 	444, 	446, 	448, 	450, 	452, 	455, 	457, 	459, 	461, 	463, 	466, 	468, 	470, 	472, 	475, 	477, 	479, 	481, 	484, 	486, 	488, 	491, 	493, 	495, 	497, 	500, 	502, 	504, 	507, 	509, 	511, 	514, 	516, 	518, 	521, 	523, 	525, 	528, 	530, 	533, 	535, 	537, 	540, 	542, 	544, 	547, 	549, 	552, 	554, 	556, 	559, 	561, 	564, 	566, 	569, 	571, 	573, 	576, 	578, 	581, 	583, 	586, 	588, 	591, 	593, 	596, 	598, 	601, 	603, 	606, 	608, 	611, 	613, 	616, 	618, 	621, 	623, 	626, 	628, 	631, 	633, 	636, 	639, 	641, 	644, 	646, 	649, 	651, 	654, 	657, 	659, 	662, 	664, 	667, 	670, 	672, 	675, 	677, 	680, 
 683, 	 685, 	 688, 	 691, 	 693, 	 696, 	 698, 	 701, 	 704, 	 706, 	 709, 	 712, 	 714, 	 717, 	 720, 	 722, 	 725, 	 728, 	 731, 	 733, 	 736, 	739, 	741, 	744, 	747, 	750, 	752, 	755, 	758, 	760, 	763, 	766, 	769, 	771, 	774, 	777, 	780, 	782, 	785, 	788, 	791, 	794, 	796, 	799, 	802, 	805, 	808, 	810, 	813, 	816, 	819, 	822, 	824, 	827, 	830, 	833, 	836, 	839, 	841, 	844, 	847, 	850, 	853, 	856, 	859, 	861, 	864, 	867, 	870, 	873, 	876, 	879, 	882, 	885, 	887, 	890, 	893, 	896, 	899, 	902, 	905, 	908, 	911, 	914, 	917, 	920, 	922, 	925, 	928, 	931, 	934, 	937, 	940, 	943, 	946, 	949, 	952, 	955, 	958, 	961, 	964, 	967, 	970, 	973, 	976, 	979, 	982, 	985, 	988, 	991, 	994, 	997, 	1000, 	1003, 	1006, 	1009, 	1012, 	1015, 	1018, 	1021, 	1024, 	1027, 	1030, 	1033, 	1036, 	1040, 	1043, 	1046, 	1049, 	1052, 	1055, 	1058, 	1061, 	1064, 	1067, 	1070, 	1073, 	1077, 	1080, 	1083, 	1086, 	1089, 	1092, 	1095, 	1098, 	1101, 	1104, 	1108, 	1111, 	1114, 	1117, 	1120, 	1123, 	1126, 	1130, 	1133, 	1136, 	1139, 	1142, 	1145, 	1148, 	1152, 	1155, 	1158, 	1161, 	1164, 	1167, 	1171, 	1174, 	1177, 	1180, 	1183, 	1187, 	1190, 	1193, 	1196, 	1199, 	1203, 	1206, 	1209, 	1212, 	1215, 	1219, 	1222, 	1225, 	1228, 	1231, 	1235, 	1238, 	1241, 	1244, 	1248, 	1251, 	1254, 	1257, 	1261, 	1264, 	1267, 	1270, 	1273, 	1277, 	1280, 	1283, 	1287, 	1290, 	1293, 	1296, 	1300, 	1303, 	1306, 	1309, 	1313, 	1316, 	1319, 	1323, 	1326, 	1329, 	1332, 	1336, 	1339, 	1342, 	1346, 	1349, 	1352, 	1355, 	1359, 	1362, 	1365, 	1369, 	1372, 	1375, 	1379, 	1382, 	1385, 	1389, 	1392, 	1395, 	1399, 	1402, 	1405, 	1409, 	1412, 	1415, 	1419, 	1422, 	1425, 	1429, 	1432, 	1435, 	1439, 	1442, 	1445, 	1449, 	1452, 	1455, 	1459
};

//  Spin Up and Down table  ---  Spin_Period determines how many times each displacement is repeated
static unsigned int DeltaPhase[34] =
{
0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33																		
};

 //  Left from Keil's CAN example  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>	
/*----------------------------------------------------------------------------
  SysTick_Handler
 *----------------------------------------------------------------------------*/
void SysTick_Handler(void)
{
  msTicks++;                        /* increment counter necessary in Delay() */
}

/*----------------------------------------------------------------------------
  delays number of tick Systicks (happens every 1 ms)
 *----------------------------------------------------------------------------*/
void Delay (uint32_t dlyTicks)
{
  uint32_t curTicks;
  curTicks = msTicks;
  while ((msTicks - curTicks) < dlyTicks);
}

/*----------------------------------------------------------------------------
  initialize CAN interface
 *----------------------------------------------------------------------------*/
/*  CAN message structure (from CAN.h)
typedef struct  {
  unsigned int   id;                 // 29 bit identifier
  unsigned char  data[8];            // Data field
  unsigned char  len;                // Length of data field in bytes
  unsigned char  format;             // 0 - STANDARD, 1- EXTENDED IDENTIFIER
  unsigned char  type;               // 0 - DATA FRAME, 1 - REMOTE FRAME
} CAN_msg;				*/

void can_Init (void) 
{
  CAN_setup ();                                   /* setup CAN Controller     */
//CAN_wrFilter (35, EXTENDED_FORMAT);             /* Enable reception of msgs */  ?????????????????
  CAN_start ();                                   /* start CAN Controller   */
  CAN_waitReady ();   //@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                            /* wait til tx mbx is empty %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%*/  ??????????????????
}		
//  End of stuff left from Keil's CAN example  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

void flash_PA6(int leng)
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	*ptr |= 0x0040;																//  Flash the PA6 LED
	Delay(leng);																	//  This makes a delay of  leng m-sec		
	*ptr &= 0xFFBF;																//  Set PA6 low again
}

void switch_PA4(int led_state)
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	if(led_state == 1){														//  Flash the PA4 and PA5 LEDs
	*ptr |= 0x0030;
	}
	
	else if(led_state == 2){
	*ptr |= 0x0010;
	*ptr &= 0xFFDF;
	}
	
	else if(led_state == 3){
	*ptr |= 0x0020;		
	*ptr &= 0xFFEF;	
	}
	
	else if (led_state == 0){																
	//*ptr &= 0xFFEF;																//  Set PA4 and PA5 low again
	*ptr &= 0xFFCF;
	}
}

int readsync_PB2()															//Read sync signal and return its value, returns 1 when sync goes low
{
	int status=0;
	GPIOB ->ODR |= 0x0004;
	
	if((GPIOB->IDR & 0x0004) == 0)
	{
		status = 1;
	}
	else
	{
		status = 0;
	}	
	return status;														
}

void send_CANmsg(int can_add, int length, int data_lower, int data_upper){					//Function for sending CAN messages from positioner
	int i;
	can_Init();																								//Not sure if this needs to be called again
	CAN_TxMsg.id=can_add;
	for(i=0; i<8; i++) CAN_TxMsg.data[i]=0;										//Zero out data field in message to be transmitted
	
	CAN_TxMsg.len=length;
	CAN_TxMsg.format = EXTENDED_FORMAT;
	CAN_TxMsg.type = DATA_FRAME;
	
	Delay (100);													    				//  Delay for 100 ms
	if(CAN_TxRdy){
		
	CAN_TxRdy=0;																			//reset CAN_TxRdy	

	CAN_TxMsg.data[0] = data_lower & 0x000000FF;
	CAN_TxMsg.data[1] = (data_lower >> 8) & 0x000000FF;
	CAN_TxMsg.data[2] = (data_lower >> 16)& 0x000000FF;
	CAN_TxMsg.data[3] = (data_lower >> 24) & 0x000000FF;
	CAN_TxMsg.data[4] = data_upper & 0x000000FF;
	CAN_TxMsg.data[5] = (data_upper >> 8) & 0x000000FF;
	CAN_TxMsg.data[6] = (data_upper >> 16)	& 0x000000FF;
	CAN_TxMsg.data[7] = (data_upper >> 24) & 0x000000FF;	
	
	CAN_wrMsg(&CAN_TxMsg);								  					//Transmit message
		
	Delay(100);														  			
	CAN_TxRdy=1;		
	} //end if(CAN_TxRdy)
}


void flash_write(unsigned short pos_id){
	unsigned long *ptr;
	unsigned short val=pos_id;
	ptr= (unsigned long *) 0x0801E800;

	//1) Initialize

	// Unlock Flash  
	while(FLASH->SR  & 0x00000001);

	if(FLASH_CR_LOCK){  
		FLASH->KEYR = 0x45670123;
		FLASH->KEYR = 0xCDEF89AB; 
	}
	//2) Erase
	FLASH->CR  |=  0x00000002;                   	// Page Erase Enabled 
	FLASH->AR   =  0x0801E800;                   	// Page Address
	FLASH->CR  |=  0x00000040;                   	// Start Erase	
	while (FLASH->SR  & 0x00000001);							// Check busy flag
	FLASH->CR  &= ~0x00000002;   									// Page Erase Disable
		
	//3) Program
	FLASH->CR  |=  0x00000001;                  	// Programming Enabled
	M16(ptr) = val;      													// Program Half Word
	while (FLASH->SR  & 0x00000001);							// Check busy flag
	FLASH->CR  &= ~0x00000001;                  	// Programming Disabled	
}

void Drop_Mtr_Cur_0(float Current)							//  This drops the current of motor 0 down to a specified value by writing
{																								//  directly to the relevant compare registers,  i.e. it does not change 
	unsigned long *ptr;														//  any of the parameters set by the Set_Currents command
	ptr = (unsigned long *) TIM1_CCR4;
	*ptr = Current * CosTable[Theta_0];			
	ptr = (unsigned long *) TIM1_CCR2;						//  
	*ptr = Current * CosTable[Theta_0 + DEL0A];		
	ptr = (unsigned long *) TIM1_CCR3;						//  
	*ptr = Current * CosTable[Theta_0 + DEL0B];
}

void Drop_Mtr_Cur_1(float Current)							//  This drops the current of motor 1 down to a specified value by writing
{																								//  directly to the relevant compare registers,  i.e. it does not change 
	unsigned long *ptr;														//  any of the parameters set by the Set_Currents command
	ptr = (unsigned long *) TIM8_CCR1;
	*ptr = Current * CosTable[Theta_1];		
	ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
	*ptr = Current * CosTable[Theta_1 + DEL1A];	
	ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
	*ptr = Current * CosTable[Theta_1 + DEL1B];	
}

/*----------------------------------------------------------------------------
  TIM1 Update interrupt handler
 *----------------------------------------------------------------------------*/
 //  This interrupt is triggered by the update to TIM1. When the interrupt occurs, the registers for both
 //  TIM1, and TIM8 are set to the values for the next period so that at the next TIM update, the values for
 //  the next step of PWM motor operation are set up.  The 3 motor phase outputs all go high at the beginning
 //  of the period when the update occurs.  Each is set low later in the 50 u-sec period to correspond to
 //  the proper PWM time so as to adjust the current in that phase to the required value
void TIM1_UP_IRQHandler(void) 
{				
	
	unsigned long *ptr;	
	ptr = (unsigned long *) GPIOA_ODR;							//	Makes a positive going sync pulse on PA7 at the start of the ISR execution
	*ptr |= 0x00000080;															//  Set this low at the end of the ISR so we can see on an oscilloscope
																									//  how long the ISR takes.  There is also an LED connected to this

	LED_Clock    += 1;															//  This flashes the PA6 LED for 50/18,000 sec every 7,200/18,000 seconds to  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
	if(LED_Clock == 1) *ptr |= 0x0040;							//  show that the processor is running and doing the ISR
	if(LED_Clock == 50)   *ptr &= 0xFFBF;						//	Set it low again
	if(LED_Clock == 7200)  LED_Clock = 0;						//	Defines the rate of flashing
	
	ptr = (unsigned long *) TIM1_SR;								//  This clears the interrupt request so it doesn't keep repeating the ISR
	*ptr &= 0xFFFFFFFE;															//  This is necessary!  Why does 0.03 work? (It actually didn't!)
	
	
	if(run_test_seq){
		ptr = (unsigned long *) TIM1_CCR4;							//  Set ptr to point at the register for Motor_0 Phase 1

		*ptr = 1000;			//  The calculated on time for Motor_0 Phase 1 is written to the compare register for TIM1 channel 4
		ptr = (unsigned long *) TIM1_CCR2;							//  Set ptr to point at the register for Motor_0 Phase 2
		*ptr = 2000;  		//The calculated on time for Motor_0 Phase 2 is written to the compare register for TIM1 channel 2	
		ptr = (unsigned long *) TIM1_CCR3;							//  Set ptr to point at the register for Motor_0 Phase 3
		*ptr = 3000;//  The calculated on time for Motor_0 Phase 3 is written to the compare register for TIM1 channel 3		

		ptr = (unsigned long *) TIM8_CCR1;							//  Set ptr to point at the register for Motor_1 Phase 1
		*ptr = 1000;			//	The calculated on time for Motor_1 Phase 1 is written to the compare register for TIM8 channel 1		
		ptr = (unsigned long *) TIM8_CCR2;							//  Set ptr to point at the register for Motor_1 Phase 2
		*ptr = 2000;//  The calculated on time for Motor_1 Phase 2 is written to the compare register for TIM8 channel 2	
		ptr = (unsigned long *) TIM8_CCR3;							//  Set ptr to point at the register for Motor_1 Phase 3
		*ptr = 3000;//  The calculated on time for Motor_1 Phase 3 is written to the compare register for TIM8 channel 3	
	}
			
	if(device_type){// if fiducial
		
		ptr = (unsigned long *) TIM1_CCR4;							//  Set ptr to point at the register for Motor_0 Phase 1

		*ptr = 4000*duty_cycle;			//  The calculated on time for Motor_0 Phase 1 is written to the compare register for TIM1 channel 4
		ptr = (unsigned long *) TIM1_CCR2;							//  Set ptr to point at the register for Motor_0 Phase 2
		*ptr = 4000*duty_cycle;  		//The calculated on time for Motor_0 Phase 2 is written to the compare register for TIM1 channel 2	
		ptr = (unsigned long *) TIM1_CCR3;							//  Set ptr to point at the register for Motor_0 Phase 3
		*ptr = 4000*duty_cycle;//  The calculated on time for Motor_0 Phase 3 is written to the compare register for TIM1 channel 3		
		
		ptr = (unsigned long *) TIM8_CCR1;							//  Set ptr to point at the register for Motor_1 Phase 1
		*ptr = 4000*duty_cycle;			//	The calculated on time for Motor_1 Phase 1 is written to the compare register for TIM8 channel 1		
		ptr = (unsigned long *) TIM8_CCR2;							//  Set ptr to point at the register for Motor_1 Phase 2
		*ptr = 4000*duty_cycle;//  The calculated on time for Motor_1 Phase 2 is written to the compare register for TIM8 channel 2	
		ptr = (unsigned long *) TIM8_CCR3;							//  Set ptr to point at the register for Motor_1 Phase 3
		*ptr = 4000*duty_cycle;//  The calculated on time for Motor_1 Phase 3 is written to the compare register for TIM8 channel 3	
	}
	
	
//  Do motor 0 first:    *************************************************************************************************************************
	if(Flags_0 & 128)																	//  MSB high means there is a CW Spin Up pending or in process
	{
		
		Theta_0 += DeltaPhase[Spin_Ptr_0];							//  Advance the motor phase by the amount read from the Spinup Table
		if(Theta_0 >= 3600)   Theta_0 -= 3600;					//  Check for roll over	
		ptr = (unsigned long *) TIM1_CCR4;							//  Set ptr to point at the register for Motor_0 Phase 1
		// Note!!! These TIMx_CCRx registers determine the rotor phase and current drawn by each motor. So standby current is set by where they are left.
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0];			//  The calculated on time for Motor_0 Phase 1 is written to the compare register for TIM1 channel 4
		ptr = (unsigned long *) TIM1_CCR2;							//  Set ptr to point at the register for Motor_0 Phase 2
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0+DEL0A];//  The calculated on time for Motor_0 Phase 2 is written to the compare register for TIM1 channel 2	
		ptr = (unsigned long *) TIM1_CCR3;							//  Set ptr to point at the register for Motor_0 Phase 3
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0+DEL0B];//  The calculated on time for Motor_0 Phase 3 is written to the compare register for TIM1 channel 3
		
		spin_count_0++;
		if(spin_count_0 >= Spin_Period) spin_count_0 = 0, Spin_Ptr_0 += 1;		//  Advance to the next Spin Up Delta Phase
	
		if(Spin_Ptr_0 >= 34)  Flags_0 &= 0x7F, spin_count_0=0, Spin_Ptr_0=33; 								//  Done with Spin Up so clear flag; Next do Cruise
	}																									//  Leave Spin Pointer at 378 because we will use it to spin down
	
	else if((Flags_0 & 64)&&(CruiseStepsToGo_0 > 0))	//  Means there is a CW Cruise pending or in process 
	{		
		Theta_0 += 33;																	//  Rotate 3.3 deg with each step for 9,900 RPM spin rate at cruise
		if(Theta_0 >= 3600)   Theta_0 -= 3600;					//  Check for roll over
		ptr = (unsigned long *) TIM1_CCR4;							//  
		*ptr = CruiseCurrent_0 * CosTable[Theta_0];			
		ptr = (unsigned long *) TIM1_CCR2;							//  
		*ptr = CruiseCurrent_0 * CosTable[Theta_0+DEL0A];		//  Note that DEL0A is either 1200 or 2400 depending on the value of the motor reverse flag, REVMTR0
		ptr = (unsigned long *) TIM1_CCR3;									//  And DEL0B is the opposite, thus REVMTR0 sets the direction of motor rotation
		*ptr = CruiseCurrent_0 * CosTable[Theta_0+DEL0B];	
		CruiseStepsToGo_0 -= 1;													//  Finished this step, so decrement number of remaining steps
		if(CruiseStepsToGo_0 == 0)  Flags_0 &= 0x3F;		//  Done with Cruise so clear flag; Next will do Spin Down 
	}
	
	else if(Flags_0 & 32)														//  Means there is a CW Spin Down pending or in process
	{	
		
		if(spin_count_0 >= Spin_Period) spin_count_0=0, Spin_Ptr_0 -= 1;
		spin_count_0++;
		
		Theta_0 += DeltaPhase[Spin_Ptr_0];						//  Advance the motor phase by the amount read from table
		if(Theta_0 >= 3600)   Theta_0 -= 3600;				//  Check for roll over
		ptr = (unsigned long *) TIM1_CCR4;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0];			
		ptr = (unsigned long *) TIM1_CCR2;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0 + DEL0A];		
		ptr = (unsigned long *) TIM1_CCR3;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0 + DEL0B];
		
		if(Spin_Ptr_0 == 0 && (spin_count_0 >= Spin_Period))														 
		{			
			Flags_0 &= 0x1F;														//  Done with Spin Down so clear flag; Next will do	Creep
			spin_count_0=0;
			Drop_Mtr_Cur_0(0.05);												//	Drop current down to 5% of stall  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
			
		}	
	}
		
	else if(Flags_0 & 16)														//  Means there is a CCW Spin Up pending or in process
	{	
		
		Theta_0 -= DeltaPhase[Spin_Ptr_0];						//  Rotate the motor phase backward by the amount read from table
		if(Theta_0 >= 3600)   Theta_0 += 3600;				//  Check for roll under  (Theta_0 is an unsigned int)
		ptr = (unsigned long *) TIM1_CCR4;						//  
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0];			
		ptr = (unsigned long *) TIM1_CCR2;						//  
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0 + DEL0A];		
		ptr = (unsigned long *) TIM1_CCR3;						//  
		*ptr = SpinUpCurrent_0 * CosTable[Theta_0 + DEL0B];
		
		spin_count_0++;
		if(spin_count_0 >= Spin_Period) spin_count_0 = 0, Spin_Ptr_0 += 1;		//  Advance to the next Spin Up Delta Phase
	
		if(Spin_Ptr_0 >= 34)  Flags_0 &= 0x0F, spin_count_0=0, Spin_Ptr_0=33; 								//  Done with Spin Up so clear flag; Next do Cruise		
		
	}	
	
	else if((Flags_0 & 8)&&(CruiseStepsToGo_0 > 0))	//  Means there is a CCW Cruise pending or in process 
	{	
	
		Theta_0 -= 33;																//  Rotate 3.3 deg backward with each step
		if(Theta_0 > 3600)   Theta_0 += 3600;					//  Check for roll under
		ptr = (unsigned long *) TIM1_CCR4;						//  
		*ptr = CruiseCurrent_0 * CosTable[Theta_0];			
		ptr = (unsigned long *) TIM1_CCR2;						//  
		*ptr = CruiseCurrent_0 * CosTable[Theta_0 + DEL0A];		
		ptr = (unsigned long *) TIM1_CCR3;						//  
		*ptr = CruiseCurrent_0 * CosTable[Theta_0 + DEL0B];
		CruiseStepsToGo_0 -= 1;												//  Finished this step, so decrement number of remaining steps
		if(CruiseStepsToGo_0 == 0)  Flags_0 &= 0x07;	//  Done with Spin Up so clear flag; Next will do Spin Down
	
	}
	
	else if(Flags_0 & 4)														//  Means there is a CCW Spin Down pending or in process
	{	
	
	  if(spin_count_0 >= Spin_Period) spin_count_0=0, Spin_Ptr_0 -= 1;
		
		spin_count_0++;
				
		Theta_0 -= DeltaPhase[Spin_Ptr_0];						//  Rotate the motor phase backward by the amount read from table
		if(Theta_0 > 3600)   Theta_0 += 3600;					//  Check for roll under
		ptr = (unsigned long *) TIM1_CCR4;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0];			
		ptr = (unsigned long *) TIM1_CCR2;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0 + DEL0A];		
		ptr = (unsigned long *) TIM1_CCR3;						//  
		*ptr = SpinDownCurrent_0 * CosTable[Theta_0 + DEL0B];
		
		
		if(Spin_Ptr_0 == 0 && ((spin_count_0) >= Spin_Period))  
		{
			Flags_0 &= 0x03;														//  Done with Spin Down so clear flag; Next will do	Creep against stop
			spin_count_0 = 0;
			Drop_Mtr_Cur_0(0.05);												//	Drop current down to 5% of stall  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
		}	
		
	}
	
	else if((Flags_0 & 2)&&(CCW_CreepStepsToGo_0 > 0))//  Means there is a CCW Low Current creep up (against the stop) pending or in process
	{	
		
		if(count_0 >= CreepPeriod_0)
		{
			count_0 = 0;
			Theta_0 -= 1;																//  Back up 0.1 deg with each step
			if(Theta_0 > 3600)   Theta_0 += 3600;				//  Check for roll under
			ptr = (unsigned long *) TIM1_CCR4;					//  
			*ptr = CCW_OpCreepCur_0 * CosTable[Theta_0];			
			ptr = (unsigned long *) TIM1_CCR2;					//  
			*ptr = CCW_OpCreepCur_0 * CosTable[Theta_0 + DEL0A];		
			ptr = (unsigned long *) TIM1_CCR3;					//  
			*ptr = CCW_OpCreepCur_0 * CosTable[Theta_0 + DEL0B];
			CCW_CreepStepsToGo_0 -= 1;
			if((CCW_CreepStepsToGo_0 <= 900)&&(Bump_CCW_Creep_Mtr_0 == 1))		//  Bump the creep current up to 100% for the last 90 degrees of the creep
			{																														//  to minimize the final phase error
				CCW_OpCreepCur_0 = 1;
			}			
			if(CCW_CreepStepsToGo_0 == 0)
			{
				Flags_0 &= 0x01;													//  Done with Find Stop so clear flag; Done with this motor rotation
				Drop_Mtr_Cur_0(M0_Drop_Cur);												//  Set motor current to a low holding value
			}
		}
		++count_0;
		
	}
	
	else if((Flags_0 & 1)&&(CW_CreepStepsToGo_0 > 0))	//  Means there is a CW Creep to final position pending or in process
	{	
		if(count_0 >= CreepPeriod_0)		
		{
			count_0 = 0;
			Theta_0 += 1;																//  Rotate 0.1 deg with each step
			if(Theta_0 >= 3600)   Theta_0 -= 3600;			//  Check for roll over
			ptr = (unsigned long *) TIM1_CCR4;					//  
			*ptr = CW_OpCreepCur_0 * CosTable[Theta_0];			
			ptr = (unsigned long *) TIM1_CCR2;					//  
			*ptr = CW_OpCreepCur_0 * CosTable[Theta_0 + DEL0A];		
			ptr = (unsigned long *) TIM1_CCR3;					//  
			*ptr = CW_OpCreepCur_0 * CosTable[Theta_0 + DEL0B];
			CW_CreepStepsToGo_0 -= 1;
			if((CW_CreepStepsToGo_0 <= 900)&&(Bump_CW_Creep_Mtr_0 == 1))		//  Bump the creep current up to 100% for the last 90 degrees of the creep
			{																														//  to minimize the final phase error
				CW_OpCreepCur_0 = 1;
			}
			if(CW_CreepStepsToGo_0 == 0)
			{
				Flags_0 &= 0x00;													//  Done with Creep so clear flag; Done with this motor rotation
				Drop_Mtr_Cur_0(M0_Drop_Cur);												//  Set motor current to a low holding value			
			}
		}
		++count_0;
	}
//  Now do motor 1:  *******************************************************************************************************************************************
	if(Flags_1 & 128)																	//  MSB high means there is a CW Spin Up pending or in process
	{
	
		Theta_1 += DeltaPhase[Spin_Ptr_1];							//  Advance the motor phase by the amount read from table
		if(Theta_1 >= 3600)   Theta_1 -= 3600;					//  Check for roll over
		ptr = (unsigned long *) TIM8_CCR1;							//  Set ptr to point at the register for Motor_1 Phase 1
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1];			//	The calculated on time for Motor_1 Phase 1 is written to the compare register for TIM8 channel 1		
		ptr = (unsigned long *) TIM8_CCR2;							//  Set ptr to point at the register for Motor_1 Phase 2
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1+DEL1A];//  The calculated on time for Motor_1 Phase 2 is written to the compare register for TIM8 channel 2	
		ptr = (unsigned long *) TIM8_CCR3;							//  Set ptr to point at the register for Motor_1 Phase 3
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1+DEL1B];//  The calculated on time for Motor_1 Phase 3 is written to the compare register for TIM8 channel 3
		
		spin_count_1++;
		if(spin_count_1 >= Spin_Period) spin_count_1 = 0, Spin_Ptr_1 += 1;		//  Advance to the next Spin Up Delta Phase
	
		if(Spin_Ptr_1 >= 34)  Flags_1 &= 0x7F, spin_count_1=0, Spin_Ptr_1=33; 								//  Done with Spin Up so clear flag; Next do Cruise
		
	}
	
	else if((Flags_1 & 64)&&(CruiseStepsToGo_1 > 0))	//  Means there is a CW Cruise pending or in process
	{	
		Theta_1 += 33;																//  Rotate 3.3 deg with each step
		if(Theta_1 >= 3600)   Theta_1 -= 3600;				//  Check for roll over
		ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
		*ptr = CruiseCurrent_1 * CosTable[Theta_1];		
		ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
		*ptr = CruiseCurrent_1 * CosTable[Theta_1 + DEL1A];	
		ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
		*ptr = CruiseCurrent_1 * CosTable[Theta_1 + DEL1B];	
		CruiseStepsToGo_1 -= 1;												//  Finished this step, so decrement number of remaining steps
		if(CruiseStepsToGo_1 == 0)  Flags_1 &= 0x3F;	//  Done with Spin Up so clear flag; Next will do Spin Down			
	}
	
	else if(Flags_1 & 32)														//  Means there is a CW Spin Down pending or in process
	{	
		if(spin_count_1 >= Spin_Period) spin_count_1=0, Spin_Ptr_1 -= 1;
		spin_count_1++;
	
		Theta_1 += DeltaPhase[Spin_Ptr_1];						//  Advance the motor phase by the amount read from table
		if(Theta_1 >= 3600)   Theta_1 -= 3600;				//  Check for roll over
		ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1];		
		ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1 + DEL1A];	
		ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1 + DEL1B];	
		if(Spin_Ptr_1 == 0 	&& (spin_count_1 >= Spin_Period))						//  Done with Spin Down so clear flag; Next will do	Creep
		{			
			Flags_1 &= 0x1F;
			spin_count_1=0;
			Drop_Mtr_Cur_1(0.05);												//	Drop current down to 5% of stall  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
		}			
	}
		
	else if(Flags_1 & 16)														//  Means there is a CCW Spin Up pending or in process
	{	

		Theta_1 -= DeltaPhase[Spin_Ptr_1];						//  Rotate the motor phase backward by the amount read from table
		if(Theta_1 > 3600)   Theta_1 += 3600;					//  Check for roll under
		ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1];		
		ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1 + DEL1A];	
		ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
		*ptr = SpinUpCurrent_1 * CosTable[Theta_1 + DEL1B];	
		
		spin_count_1++;
		if(spin_count_1 >= Spin_Period) spin_count_1 = 0, Spin_Ptr_1 += 1;		//  Advance to the next Spin Up Delta Phase
	
		if(Spin_Ptr_1 >= 34)  Flags_1 &= 0x0F, spin_count_1=0, Spin_Ptr_1=33; 								//  Done with Spin Up so clear flag; Next do Cruise				
	}	
	
	else if((Flags_1 & 8)&&(CruiseStepsToGo_1 > 0))													//  Means there is a CCW Cruise pending or in process
	{	
		Theta_1 -= 33;																//  Rotate 3.3 deg backward with each step
		if(Theta_1 > 3600)   Theta_1 += 3600;					//  Check for roll under
		ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
		*ptr = CruiseCurrent_1 * CosTable[Theta_1];		
		ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
		*ptr = CruiseCurrent_1 * CosTable[Theta_1 + DEL1A];	
		ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
		*ptr = CruiseCurrent_1 * CosTable[Theta_1 + DEL1B];	
		CruiseStepsToGo_1 -= 1;												//  Finished this step, so decrement number of remaining steps
		if(CruiseStepsToGo_1 == 0)  Flags_1 &= 0x07;	//  Done with Spin Up so clear flag; Next will do Spin Down				
	}
	
	else if(Flags_1 & 4)														//  Means there is a CCW Spin Down pending or in process
	{	
		if(spin_count_1 >= Spin_Period) spin_count_1 = 0, Spin_Ptr_1 -= 1;
		spin_count_1++;

		Theta_1 -= DeltaPhase[Spin_Ptr_1];						//  Rotate the motor phase backward by the amount read from table
		if(Theta_1 > 3600)   Theta_1 += 3600;					//  Check for roll under
		ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1];		
		ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1 + DEL1A];	
		ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
		*ptr = SpinDownCurrent_1 * CosTable[Theta_1 + DEL1B];	
		
		if(Spin_Ptr_1 == 0 && (spin_count_1 >= Spin_Period)) 
		{
			Flags_1 &= 0x03;														//  Done with Spin Down so clear flag; Next will do	Creep	
			spin_count_1=0;
			Drop_Mtr_Cur_1(0.05);												//	Drop current down to 5% of stall  @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
		}		
	}
	
	else if((Flags_1 & 2)&&(CCW_CreepStepsToGo_1 > 0)) //  Means there is a CCW Low Current creep up against the stop pending or in process
	{	
		if(count_1 >= CreepPeriod_1)		
		{
			count_1 = 0;		
			Theta_1 -= 1;																	//  Back up 0.1 deg with each step
			if(Theta_1 > 3600)   Theta_1 += 3600;					//  Check for roll under
			ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
			*ptr = CCW_OpCreepCur_1 * CosTable[Theta_1];		
			ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
			*ptr = CCW_OpCreepCur_1 * CosTable[Theta_1 + DEL1A];	
			ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
			*ptr = CCW_OpCreepCur_1 * CosTable[Theta_1 + DEL1B];	
			CCW_CreepStepsToGo_1 -= 1;
			if((CCW_CreepStepsToGo_1 <= 900)&&(Bump_CCW_Creep_Mtr_1 == 1))	//  Bump the creep current up to 100% for the last 90 degrees of the creep
			{																																//  to minimize the final phase error
				CCW_OpCreepCur_1 = 1;
			}
			if(CCW_CreepStepsToGo_1 == 0)
			{
				Flags_1 &= 0x1;															//  Done with Find Stop so clear flag; Done with this motor rotation
				Drop_Mtr_Cur_1(M1_Drop_Cur);								//  Set motor current to a low holding value
			}
		}
		++count_1;		
	}
	
	else if((Flags_1 & 1)&&(CW_CreepStepsToGo_1 > 0))		//  Means there is a CW Creep to final position pending or in process
	{	
		if(count_1 >= CreepPeriod_1)		
		{
			count_1 = 0;
			Theta_1 += 1;																	//  Rotate 0.1 deg with each step
			if(Theta_1 >= 3600)   Theta_1 -= 3600;				//  Check for roll over
			ptr = (unsigned long *) TIM8_CCR1;						//  This is the compare register for TIM8 channel 1
			*ptr = CW_OpCreepCur_1 * CosTable[Theta_1];		
			ptr = (unsigned long *) TIM8_CCR2;						//  This is the compare register for TIM8 channel 2
			*ptr = CW_OpCreepCur_1 * CosTable[Theta_1 + DEL1A];	
			ptr = (unsigned long *) TIM8_CCR3;						//  This is the compare register for TIM8 channel 3
			*ptr = CW_OpCreepCur_1 * CosTable[Theta_1 + DEL1B];	
			CW_CreepStepsToGo_1 -= 1;
			if((CW_CreepStepsToGo_1 <= 900)&&(Bump_CW_Creep_Mtr_1 == 1))	//  Bump the creep current up to 100% for the last 90 degrees of the creep
			{																															//  to minimize the final phase error
				CW_OpCreepCur_1 = 1;
			}
			if(CW_CreepStepsToGo_1 == 0)
			{
				Flags_1 &= 0x00;														//  Done with Creep; clear flag; Done with this motor rotation
				Drop_Mtr_Cur_1(M1_Drop_Cur);								//  Set motor current to a low holding value
			}
		}
		++count_1;		
	}
	if(Set_Flags)																			//  This is to insure that an interrupt doesn't occur when the flags
	{																									//  are only partially set up	
		Set_Flags = 0;		
		CW_OpCreepCur_0 = CreepCurrent_0;								//  Set the creep current to the commanded value.  This was set to 1
																										//  for the last 90 degrees of the last creep
		CW_OpCreepCur_1 = CreepCurrent_1;								//  Set the creep current to the commanded value
		
		CCW_OpCreepCur_0 = CreepCurrent_0;							//   
		CCW_OpCreepCur_1 = CreepCurrent_1;							//  

		Flags_0 = Sh_Fl_0;
		Flags_1 = Sh_Fl_1;
		Sh_Fl_0 = 0;																		//  So it doesn't repeat the same thing the next time
		Sh_Fl_1 = 0;
		Set_Flags = 0;
	}
	
		if(Set_Flags_0)																	//  This is to insure that an interrupt doesn't occur when the flags
	{																									//  are only partially set up		
		Set_Flags_0 = 0;	
		CW_OpCreepCur_0 = CreepCurrent_0;								//  Set the creep current to the commanded value.  This was set to 1
																										//  for the last 90 degrees of the last creep
		CCW_OpCreepCur_0 = CreepCurrent_0;							//   		
		Flags_0 = Sh_Fl_0;
		Sh_Fl_0 = 0;																		//  So it doesn't repeat the same thing the next time
		
	}
	
	if(Set_Flags_1)																		//  This is to insure that an interrupt doesn't occur when the flags
	{																									//  are only partially set up	
		Set_Flags_1 = 0;	
		CW_OpCreepCur_1 = CreepCurrent_1;								//  Set the creep current to the commanded value
		CCW_OpCreepCur_1 = CreepCurrent_1;							//  	
		Flags_1 = Sh_Fl_1;
		Sh_Fl_1 = 0;			
	}
	
	ptr = (unsigned long *) GPIOA_ODR;								//	Set PA7 low again so can see the end of the ISR on oscilloscope
	*ptr &= 0xFFFFFF7F;																//	
}	   

/*----------------------------------------------------------------------------
  Other Functions used in main
 *----------------------------------------------------------------------------*/

void Set_Initial_Taus(void)
{
	unsigned long *ptr;	
	Theta_0 = Offset_0;
	ptr = (unsigned long *) TIM1_CCR4;						//  Tau0_1 is written to the compare register for TIM1 channel 4
	*ptr = 0.1 * CosTable[Theta_0];		
	ptr = (unsigned long *) TIM1_CCR2;						//  Tau0_2 is written to the compare register for TIM1 channel 2
	*ptr = 0.1 * CosTable[Theta_0 + DEL0A];	
	ptr = (unsigned long *) TIM1_CCR3;						//  Tau0_3 is written to the compare register for TIM1 channel 3
	*ptr = 0.1 * CosTable[Theta_0 + DEL0B];	
	
	Theta_1 = Offset_1;
	ptr = (unsigned long *) TIM8_CCR1;						//  Tau1_1 is written to the compare register for TIM8 channel 1
	*ptr = 0.1 * CosTable[Theta_1];			
	ptr = (unsigned long *) TIM8_CCR2;						//  Tau1_2 is written to the compare register for TIM8 channel 2
	*ptr = 0.1 * CosTable[Theta_1 + DEL1A];	
	ptr = (unsigned long *) TIM8_CCR3;						//  Tau1_3 is written to the compare register for TIM8 channel 3
	*ptr = 0.1 * CosTable[Theta_1 + DEL1B];		
}

/*
  Setting Alternate GPIO Functions:
	GPIOx_CRL = 0xSSSSSSS9    9 sets I/O bit 0 to the alternate function with a 10Mhz speed capability
	(use 0xA for a 2 MHz capability and lower power comsumption).
	Currently using PA9, PA10, and PA11 FOR TIM1;  and PC6, PC7, and PC8, FOR TIM8
*/

void Set_Up_Standard_GPIO(void)									//  Sets up the GPIO ports which are used as ordinary inputs or outputs:
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOB_CRH;						//  Set PB10 as output  #######################################################
	*ptr &= 0xFFFFF0FF;														//  It needs this to receive CAN messages because I have PB10 connected to RS
	*ptr |= 0x00000100;														//  (sleep) on the CAN interface IC
	
	ptr = (unsigned long *) GPIOB_CRL;						//  Set PB5 as output to use as Switch Enable in production version PCB
																								//  Set PB2 as input to use as Sync, pull down (write 0 to ODR for PB2)
	*ptr &= 0xFF0FF0FF;
	*ptr |= 0x00100800;
	
	ptr = (unsigned long *) GPIOA_CRL;						//  Set PA3-7 as output    (PA4-7 have LED's on BB-0200), set PA0-2 as analog input for ADC
	*ptr = 0x11111000;
}

void Set_Up_Alt_GPIO(void)											//  Set up the Alternate GPIO Functions:
{																								//  See RM0008 Rev. 14 starting on page 166
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_CRH;
	*ptr &= 0xFFFF0000;													//  Sets 'alternative functions' for PA8, PA9, PA10 and PA11 (non-remapped outputs for TIM1 CH's)
	*ptr |= 0x00009999;													//  '9' gives the alternative function with 10Mhz outputs  (probably can use 'A' which gives max
																							//  speed of 2 Mhz and takes less power)
	ptr = (unsigned long *) GPIOC_CRL;
	*ptr &= 0x00FFFFFF;													//  Sets 'alternative functions' for PC6 and PC7 (non-remapped TIM8 CH1 & CH2)
	*ptr |= 0x99000000;

	ptr = (unsigned long *) GPIOC_CRH;
	*ptr &= 0xFFFFFF00;													//  Sets 'alternative functions' for PC8 and PC9 (non-remapped TIM8 CH3 & CH4)
	*ptr |= 0x00000099;
}	

void Set_Up_Timer_Regs(void)										//  Set up the timer control registers
{																								//  See RM0008 Rev. 14 starting on page 388
		unsigned long *ptr;
// Set up TIM1
		ptr = (unsigned long *) TIM1_CR1;						//  Set this to 0x85,  Bit 7 is Auto Relaod Pre-load Enable;  bit 2 = 1 means only Timer overflows or updates
		*ptr = 0x85;																//  generate an interrupt;  bit 0 enables the counter to count.  (I'm not sure about bit 2 -- but it seems to be necessary)
		ptr = (unsigned long *) TIM1_DIER;  				//  This enables various Interrupts.   Bits 1,2,3,4 are compare flags; 
		*ptr = 0x1;																	//  bit 0 is Update flag. We want to interrupt on Update,  not on Compare
		ptr = (unsigned long *)	TIM1_SR;						//  These are rc_w0; Bit 0 of this is the Update Interrupt Flag. You don't set them;
																								//	but you have to clear bit 0 in the ISR or it will keep re-interrupting
		ptr = (unsigned long *) TIM1_EGR;						//  Not clear;  maybe bit 0 = 1 to have auto update of counter?
		*ptr = 0x1;
		ptr = (unsigned long *) TIM1_CCMR1;					//  Set to 0X6868  to set up for compare CH2 and CH1
		*ptr = 0x6868;
		ptr = (unsigned long *) TIM1_CCMR2;					//  Set to 0X6868  to set up for compare CH4 and CH3
		*ptr = 0x6868;
		ptr = (unsigned long *) TIM1_CCER;					//  Set to 0X1111  to make all compare outputs active high and connected to
		*ptr = 0x1111;															//  the output port pins
		ptr = (unsigned long *) TIM1_PSC;						//	Set this to zero for a pre-scale divide count of one
		*ptr = 0;
		ptr = (unsigned long *) TIM1_ARR;						//	Set the main count for each timer to TIMDIV which currently equals 4000;
		*ptr = TIMDIV;															//  With a 72 Mhz clock, that gives a PWM rate of 18 Khz
		ptr = (unsigned long *) TIM1_BDTR;					//  Need this to enable compare outputs	
		*ptr = 0XC000;		
		ptr = (unsigned long *) TIM1_CCR1;					//  This is the compare register for TIM1 channel 1
		*ptr = 1500;																//  Set this to provide a 15/40 duty cycle reference signal on PA8 for de-bugging
		
																								//  Set up TIM8 same as for TIM1
		ptr = (unsigned long *) TIM8_CR1;
		*ptr = 0x85;	
		ptr = (unsigned long *) TIM8_DIER;
		*ptr = 0x1;												
		ptr = (unsigned long *)	TIM8_SR;
		ptr = (unsigned long *) TIM8_EGR;
		*ptr = 0x1;	
		ptr = (unsigned long *) TIM8_CCMR1;
		*ptr = 0x6868;
		ptr = (unsigned long *) TIM8_CCMR2;
		*ptr = 0x6868;
		ptr = (unsigned long *) TIM8_CCER;
		*ptr = 0x1111;
		ptr = (unsigned long *) TIM8_PSC;
		*ptr = 0;
		ptr = (unsigned long *) TIM8_ARR;
		*ptr = TIMDIV;
		ptr = (unsigned long *) TIM8_BDTR;
		*ptr = 0XC000;
}

void Set_Up_CAN_Filters(void)
{
	unsigned long *ptr;
	unsigned short i = 0;
	
	// Cancel whatever filter they have set up, and set up one which accepts only the positioner with ID = pos_id but with any type code
// First deactivate their filter(s)
	ptr = (unsigned long *) CAN_FMR;		//  The FINIT bit has to be set = '1' to allow change of CAN_FA1R
	*ptr |= 0x00000001;									//  (This is the FINIT bit)
	ptr = (unsigned long *) CAN_FA1R;		//  Point to the register which selects which filters are active
	*ptr &= 0xFFFFC000;									//  This should disable all 14 filters
	ptr = (unsigned long *) CAN_FMR;		//  Now put the FINIT bit low again to activate the chosen filters (which is none of them)
	*ptr &=0xFFFFFFFE;
// Now set up a filter which accepts only CAN messages with ID = pos_id
	ptr = (unsigned long *) CAN_FMR;		//  
	*ptr |= 0x00000001;									//  The FINIT bit has to be set = '1' to allow change of CAN_FA1R
	ptr = (unsigned long *) CAN_FA1R;		//  Point to the register which selects which filters are active
	*ptr |= 0x00000003;									//  Enable filter 0 & 1
	ptr = (unsigned long *) CAN_FFA1R;	//  Assign Filter 0 to FIFO 0 (i.e. messages which get thru this filter will end up in FIFO 0 as opposed to FIFO 1)
	*ptr &= 0xFFFFFFFC;									// Set FFA0 to '0', Set FFA1 '0'
	ptr = (unsigned long *) CAN_FS1R;		// Set Filter 0 to be a single 32 bit scale configuration//
	*ptr |= 0x00000003;									// Set FSC0 to '1', Set FSC1 to '1'
	ptr = (unsigned long *) CAN_FM1R;		// Set Filter 0 for Identifier Mask Mode//
	*ptr &= 0xFFFFFFFC;									// Set FBM0 to '0', Set FBM1 to '0'
	
//  Set up the filter Identifier and Mask  (see p.640 and 668 among others)
	ptr = (unsigned long *) 0x0801E800;	// Set to address of page 61 in flash
	i=*ptr;
	i=(unsigned short) i;
	pos_id=i;
	
	ptr = (unsigned long *) CAN_F0R1;		// Set up filter 0 as a mask which accepts only the positioner specified by pos_id
	*ptr = (i << 11) + 4;								// This is the IDENTIFIER we are looking to accept (the 4 is to set IDE)  (see p.640, 662, 668 for the structure of this)
	
	ptr = (unsigned long *) CAN_F0R2;		// This is the MASK.  
	*ptr = 0xFFFFF806;									// Mask bit of '0' accepts either 1 or 0 in that bit; we have 1's for the Positioner ID and for IDE and RTR
	
	i=20000;
	ptr = (unsigned long *) CAN_F1R1;		// Set up filter 0 as a mask which accepts only the positioner specified by pos_id
	*ptr = (i << 11) + 4;								// This is the IDENTIFIER we are looking to accept (the 4 is to set IDE)  (see p.640, 662, 668 for the structure of this)
	
	ptr = (unsigned long *) CAN_F1R2;		// This is the MASK.  
	*ptr = 0xFFFFF806;									// Mask bit of '0' accepts either 1 or 0 in that bit; we have 1's for the Positioner ID and for IDE and RTR
	
	ptr = (unsigned long *) CAN_FMR;		// Finally activiate the filters again
	*ptr &=0xFFFFFFFC;									// Put the FINIT bit low again to activate Filter 0
}
 
unsigned long Get_UID_Lower(void){
	
	unsigned long *ptr;
	unsigned long uid = 0x00000000;

	ptr = (unsigned long *) 0x1FFFF7E8;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid |= (data & 0x0F);
	uid |= (data_upper << 4);

	ptr = (unsigned long *) 0x1FFFF7EC;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid |= ((data & 0x0F)<<6);
	uid |= (data_upper << 10);
			
	ptr = (unsigned long *) 0x1FFFF7ED;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid |= (data & 0x0F) << 12;
	uid |= (data_upper << 16);
	
	ptr = (unsigned long *) 0x1FFFF7EE;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid |= (data & 0x0F) << 18;
	uid |= (data_upper << 22);

	ptr = (unsigned long *) 0x1FFFF7EF;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid |= (data & 0x0F) << 24;
	uid |= (data_upper << 28);					
	return(uid);
}	
	
unsigned long Get_UID_Upper(unsigned long uid, int send){
	
	unsigned long *ptr;
	unsigned long uid_upper = 0x00000000;

	ptr = (unsigned long *) 0x1FFFF7F0;		
	data =*ptr;			
	data=(unsigned char) data;
	uid_upper |= data;
	
	ptr = (unsigned long *) 0x1FFFF7F1;		
	data =*ptr;			
	data=(unsigned char) data;
	uid_upper |= (data << 8);

	ptr = (unsigned long *) 0x1FFFF7F2;		
	data =*ptr;			
	data=(unsigned char) data;
	uid_upper |= (data << 16);

	ptr = (unsigned long *) 0x1FFFF7F3;		
	data =*ptr;			
	data=(unsigned char) data;
	data_upper = (data >> 4) & 0x0F;
	if(data_upper == 3) data_upper=0;
	else if(data_upper == 4) data_upper=1;
	else data_upper=2;
	uid_upper |= ((data & 0x0F) << 24);
	uid_upper |= (data_upper << 28);
	
	if(send) send_CANmsg(pos_id, 8, uid, uid_upper);		
	return(uid_upper);
}

/*----------------------------------------------------------------------------
  MAIN function
 *----------------------------------------------------------------------------*/
int main (void)
{	
	unsigned long *ptr;
	unsigned short i = 0;
	
	unsigned long uid;
	unsigned long uid_upper;
	
	ptr = (unsigned long *) RCC_APB2ENR;  				// Turn on clocks to AFIOEN (bit0), IOPA (bit2),
	*ptr |= 0x0000AF3D;									  				// IOPB (bit3), IOPC (bit4), IOPD (bit5), IOPG (bit8),  TIM1 (bit11),  and TIM8 (bit13).

	Set_Up_Standard_GPIO();
	
	ptr = (unsigned long *) GPIOB_ODR;   					// Set PB5 high to enable motor driver switches
	*ptr |= 0x00000020;
	
//  Left from Keil's CAN example  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>		
  SysTick_Config(SystemCoreClock / 1000);       // SysTick 1 msec IRQ       
  can_Init ();                                  // initialize CAN interface 
//  Left from Keil's CAN example  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
	
	Set_Up_CAN_Filters();
	
//	Set_Up_EXTI_Regs();   											//	These are currently used only for the demonstration/test sequences
	Set_Up_Alt_GPIO();														//  Set up the Alternate GPIO Functions (Note that we are not doing any of the remapping shown on page 177)
	Set_Up_Timer_Regs();													//  Set up the timer control registers
	Set_Initial_Taus();														//  This sets the PWM outputs to the initial offset phase
																								//  Enable Needed Interrupts
	NVIC_EnableIRQ(TIM1_UP_IRQn); 								//  TIM1_UP_IRQn is the interrupt number which is 25;  for TIM8_up_IRQn  it's 44
	
	readsync_PB2();																//  To prevent initialization glitch
//  Now sit and wait for a Timer Update interrupt, an EXTIx interrupt, or a CAN interrupt
	while (1)
	{			
		int command = 0;										//  This is a number between 0 and 255 which defines the command sent in the CAN message
																				//  It is the LS 8 bits of the IDENTIFIER
		unsigned long data_rcv;
		unsigned long data_upper_rcv;
	
		int type = 0;
		int execute_now=0;									//This will be set in the code whenever we want to execute a command right away rather than waiting for a sync signal
		int execute_code=0;									//This is defined by the CAN messages, as they are received, and specifies if a command is part of a move table, a single command or the last command of a move table
		
																				//Max size of CAN message array (number of commands to upload before executing via sync)	
    Delay (0);                  	 		   
		if (!done){
			bit_sum=0;
		for(i=0; i < stack_size; i++){
			while(!CAN_RxRdy);								//  I.e. a CAN message received interrupt has occurred
				CAN_RxRdy = 0;
			  execute_now = 0;
			
				//flash_PA6(50);									//  Flash PA6 for 50 msec when a CAN message is recognized
			
				CAN_Com_Stack[i] = CAN_RxMsg;
			
				command = CAN_Com_Stack[i].id &= 0xFF;
			 
			if(command == 4  && !legacy_test_mode){						//If command is 4 (move table command)	 		
				execute_code = (CAN_Com_Stack[i].data[0] >> 4) & 0x3;				
				switch(execute_code)
				{				
					case 0:											//single command, don't wait for sync just execute immediately
							execute_now=1;
							i=stack_size;						//exit for loop and begin executing immediately 
							stack_size=1;						//single command will be executed in execute loop
							bit_sum_match=1;
						break;
					
					case 1:											//command is part of move table, but not last command --- keep filling move table
							
							bit_sum = bit_sum + (CAN_Com_Stack[i].data[0] + 65536*CAN_Com_Stack[i].data[1] + 256*CAN_Com_Stack[i].data[2] + CAN_Com_Stack[i].data[3] + 256*CAN_Com_Stack[i].data[4] + CAN_Com_Stack[i].data[5] + command);
							
						break;
					
					case 2:											//command is last command of move table, finished filling move table -- begin waiting for sync					
																			//exit for loop and wait for sync 
							stack_size = i+1;				//all commands that have been uploaded will now be executed
							bit_sum = bit_sum + (CAN_Com_Stack[i].data[0] + 65536*CAN_Com_Stack[i].data[1] + 256*CAN_Com_Stack[i].data[2] + CAN_Com_Stack[i].data[3] + 256*CAN_Com_Stack[i].data[4] + CAN_Com_Stack[i].data[5] + command);
							i=stack_size;	
									
						break;
				}//end switch
			}// end if command 4
				
			else if(command == 16 && !legacy_test_mode){		//set up fiducial command as synchronized
				i=stack_size;
				stack_size=1;
				bit_sum_match=1;					
			}
			
			else{														//data request or testing command, these will be executed immediately rather than as part of a move table				
				execute_now=1;
				i=stack_size;
				stack_size=1;
				bit_sum_match=1;			
			}//end else
			}// end for loop
			done=1;
		}// end if !done
		
		if(CAN_RxRdy && done){//for executing move table on command or checking move table status, will be accessed when positioner is waiting for sync
			CAN_RxRdy=0;
			command=CAN_RxMsg.id &= 0xFF;
			if (command == 7) execute_now = 1;  //if execute movetable command has been sent, set execute_now flag and begin execution without waiting for sync
			
			else if (command == 13){		//if movement status, respond with movement status (0 = not moving, 1= moving)
				data=0;
				if((Flags_0) || (Flags_1))	data=1;
				if(Set_Flags || Set_Flags_0 || Set_Flags_1) data=1;;
				send_CANmsg(pos_id, 1, data,0);		
			}
			
			else if(command == 8){ //check bitsum match, if no match will reset move table
				data = (CAN_RxMsg.data[0] * 16777216) + (CAN_RxMsg.data[1] * 65536) + (CAN_RxMsg.data[2] * 256) + CAN_RxMsg.data[3];  //received bit sum
				if(data == bit_sum){
					type=1;								//move table received, bitsum match
					bit_sum_match=1;
				}	
				else{
					type=2;								//move table received, bitsum mismatch
					done=0;								//reset previously received move table, positioner will now be ready to accept new commands rather than waiting for sync
				}							
				send_CANmsg(pos_id, 5, bit_sum, type);				//positioner status sent back, with computed bitsum 
				bit_sum=0;							//reset bit sum
			}//else if check bitsum match
		}
			
			if(done && (readsync_PB2() || execute_now) && bit_sum_match){			//if done filling move table as specified by CAN commands and either sync signal or immediate execution flag has been set
			
			execute_now=0;
			bit_sum_match=0;								//reset bit_sum_match
				
			for(i=0; i<stack_size; i++){		//loop that executes the commands in the move table		
			//flash_PA6(50);
					
			command = CAN_Com_Stack[i].id &= 0xFF;	//  The command type is the 8 LSB's of the CAN message IDENTIFIER
			switch(command)													//  The switch runs the program selected by command
			{				
				case 2:																//  set_currents (Sets 8 current parameters)		
					if(!legacy_test_mode){
						SpinUpCurrent_0   = (float) CAN_Com_Stack[i].data[0]/100;
						SpinDownCurrent_0 = SpinUpCurrent_0;
						CruiseCurrent_0   = (float) CAN_Com_Stack[i].data[1]/100;
						CreepCurrent_0    = (float) CAN_Com_Stack[i].data[2]/100;
						M0_Drop_Cur = (float)  CAN_Com_Stack[i].data[3]/100;
				
						SpinUpCurrent_1   = (float) CAN_Com_Stack[i].data[4]/100;
						SpinDownCurrent_1 = SpinUpCurrent_1;
						CruiseCurrent_1   = (float) CAN_Com_Stack[i].data[5]/100;
						CreepCurrent_1    = (float) CAN_Com_Stack[i].data[6]/100;
						M1_Drop_Cur = (float) CAN_Com_Stack[i].data[7]/100;
					}
					else{
						SpinUpCurrent_0   = (float) CAN_Com_Stack[i].data[0]/100;
						SpinDownCurrent_0 = SpinUpCurrent_0;
						CruiseCurrent_0   = (float) CAN_Com_Stack[i].data[1]/100;
						CreepCurrent_0    = (float) CAN_Com_Stack[i].data[2]/100;
						//CCW_CreepCurrent_0 = (float) CAN_Com_Stack[i].data[3]/100;
						SpinUpCurrent_1   = (float) CAN_Com_Stack[i].data[4]/100;
						SpinDownCurrent_1 = SpinUpCurrent_1;
						CruiseCurrent_1   = (float) CAN_Com_Stack[i].data[5]/100;
						CreepCurrent_1    = (float) CAN_Com_Stack[i].data[6]/100;
						//CCW_CreepCurrent_1 = (float) CAN_Com_Stack[i].data[7]/100;
					}
					break;
					
				case 3:															//  set_periods (Sets 4 parameters which use 2 bytes each)
					if(!legacy_test_mode){
						CreepPeriod_0  = CAN_Com_Stack[i].data[0];
						CreepPeriod_1 = CAN_Com_Stack[i].data[1];
						Spin_Period = CAN_Com_Stack[i].data[2];
				  }
					else{
						CreepPeriod_0    = (CAN_Com_Stack[i].data[0] * 256) + CAN_Com_Stack[i].data[1];
						//CCW_CreepPeriod_0 = (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
						CreepPeriod_1    = (CAN_Com_Stack[i].data[4] * 256) + CAN_Com_Stack[i].data[5];
						//CCW_CreepPeriod_1 = (CAN_Com_Stack[i].data[6] * 256) + CAN_Com_Stack[i].data[7];
					}
					break;
							
				case 4:																//  set_move_amounts 
																							//  CW_CreepStepsToGo, CCW_CreepStepsToGo, and CruiseStepsToGo amounts are set individually for motor 0 and motor 1.
																							//  Arguments are:  execute code, select flags, 4 bytes of data that represent the selected amount.	
					if(!legacy_test_mode){
						type = CAN_Com_Stack[i].data[0] & 0xF;
						execute_code = (CAN_Com_Stack[i].data[0] >> 4) & 0x3;
						if(type == 4){											//if axis is 1, mode=creep, and direction = CW,0
								CW_CreepStepsToGo_1= (CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CW_CreepStepsToGo_1;
								type=4;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
									
								//flags for M1 creep CW
								Flag_Status_1=1;
								Sh_Fl_1=1;					
						}
									
						else if (type == 5){ 								//if axis 1, mode=creep, direction = CCW,1
								CCW_CreepStepsToGo_1=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CCW_CreepStepsToGo_1;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
											
								//flags for M1 Creep CCW
								Flag_Status_1=1;
								Sh_Fl_1=2;			
						}
					
						else if(type == 6){									//if axis is 1, mode=cruise, CW
								CruiseStepsToGo_1=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CruiseStepsToGo_1;
								type=6;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M1 cruise CW
								Flag_Status_1=1;
								Sh_Fl_1=224;							
						}
					
						else if(type == 7){								//if axis is 1, mode=cruise, CCW
								CruiseStepsToGo_1=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CruiseStepsToGo_1;
								type=6;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M1 cruise CCW
								Flag_Status_1=1;
								Sh_Fl_1=28;								
						}				
					
						else if(type == 0){									//if axis is 0, mode=creep, and direction = CW,0
								CW_CreepStepsToGo_0=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CW_CreepStepsToGo_0;
								type=0;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M0 creep CW
								Flag_Status_0=1;
								Sh_Fl_0=1;	  
						}					
					
						else if (type == 1){ 								//if axis 0, mode=creep, direction = CCW,1
								CCW_CreepStepsToGo_0=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CCW_CreepStepsToGo_0;
								type=1;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M0 creep CCW
								Flag_Status_0=1;
								Sh_Fl_0=2;						
						}
					
						else if(type == 2){								//if axis is 0, mode=cruise
								CruiseStepsToGo_0=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CruiseStepsToGo_0;
								type=2;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M0 cruise CW
								Flag_Status_0=1;
								Sh_Fl_0=224;											
						}				
					
						else if(type == 3){								//if axis is 0, mode=cruise
								CruiseStepsToGo_0=(CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
								data=CruiseStepsToGo_0;
								type=2;
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
						
								//flags for M0 cruise CCW
								Flag_Status_0=1;
								Sh_Fl_0=28;							
						}		

						else if(type == 8){							//if just a pause is desired
								post_pause = CAN_Com_Stack[i].data[4]*256 + CAN_Com_Stack[i].data[5];
								Delay(post_pause);
								post_pause=0;
						}	
					
						//Set flags now unless next command needs to be set up first.
						if(post_pause != 0){
								if(CruiseStepsToGo_0 == 0)				Sh_Fl_0 &= 0xB7;		//  This fixes the hang-up which occurred if a Start command was sent with the 
								if(CW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFE;		//  corresponding cruise or creep steps set to zero.  And it does it without adding
								if(CCW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFD;		//  anything to the timer ISR.				
								if(CruiseStepsToGo_1 == 0)				Sh_Fl_1 &= 0xB7;
								if(CW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFE;
								if(CCW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFD;				
						
								if(Flag_Status_0 && Flag_Status_1) Set_Flags=1;
								else if(Flag_Status_0 && !Flag_Status_1) Set_Flags_0=1;
								else if(!Flag_Status_0 && Flag_Status_1) Set_Flags_1=1;
						
								Flag_Status_0 = Flag_Status_1 = 0;						
						}
					
						else if((execute_code == 0 || execute_code == 2) && (type != 8)){
								if(CruiseStepsToGo_0 == 0)				Sh_Fl_0 &= 0xB7;		//  This fixes the hang-up which occurred if a Start command was sent with the 
								if(CW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFE;		//  corresponding cruise or creep steps set to zero.  And it does it without adding
								if(CCW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFD;		//  anything to the timer ISR.				
								if(CruiseStepsToGo_1 == 0)				Sh_Fl_1 &= 0xB7;
								if(CW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFE;
								if(CCW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFD;
										
								//Set_Flags for single command or last command in move table even if post_pause is 0
								if(Flag_Status_0 && Flag_Status_1) Set_Flags=1;
								else if(Flag_Status_0 && !Flag_Status_1) Set_Flags_0=1;
								else if(!Flag_Status_0 && Flag_Status_1) Set_Flags_1=1;
							
								Flag_Status_0 = Flag_Status_1 = 0;				
						}
					
						Delay(post_pause);  																			//Wait specified time before executing next command	
					}
					else{
						//M0CW_Drop_Cur   			= (float) CAN_Com_Stack[i].data[0]/100;
						//M0CCW_Drop_Cur   			= (float) CAN_Com_Stack[i].data[1]/100;
						//M1CW_Drop_Cur    			= (float) CAN_Com_Stack[i].data[2]/100;
						//M1CCW_Drop_Cur 				= (float) CAN_Com_Stack[i].data[3]/100;
				
						if(CAN_Com_Stack[i].data[4] & 32)   Bump_CW_Creep_Mtr_0 = 1;
						else  Bump_CW_Creep_Mtr_0 = 0;	
						if(CAN_Com_Stack[i].data[4] & 16)   Bump_CCW_Creep_Mtr_0 = 1;
						else  Bump_CCW_Creep_Mtr_0 = 0;	
						if(CAN_Com_Stack[i].data[4] & 2)   Bump_CW_Creep_Mtr_1 = 1;
						else  Bump_CW_Creep_Mtr_1 = 0;	
						if(CAN_Com_Stack[i].data[4] & 1)   Bump_CCW_Creep_Mtr_1 = 1;
						else  Bump_CCW_Creep_Mtr_1 = 0;	
					}
					break;					

				case 5:															//set_reset_leds
					if(!legacy_test_mode){
						type=CAN_Com_Stack[i].data[0];
						switch_PA4(type);		
					}
					else{
							CruiseStepsToGo_0    =(CAN_Com_Stack[i].data[0] * 256) + CAN_Com_Stack[i].data[1];	// Specified Motor 0 Cruise Rotation in units of 3.3 degrees
							CW_CreepStepsToGo_0  =(CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];	// Specified Motor 0 CW Creep Rotation in units of 3.3 degrees
							CruiseStepsToGo_1    =(CAN_Com_Stack[i].data[4] * 256) + CAN_Com_Stack[i].data[5];	// Specified Motor 1 Cruise Rotation in units of 0.1 degrees
							CW_CreepStepsToGo_1  =(CAN_Com_Stack[i].data[6] * 256) + CAN_Com_Stack[i].data[7];	// Specified Motor 1 CW Creep Rotation in units of 0.1 degrees
					}
					break;
				
				case 6:															//run_test_sequence
					if(!legacy_test_mode){
						run_test_seq = !run_test_seq;			//set or reset flag for sending test patterns to motor pads, will be executed in interrupt handler		
					}
					else{
							CCW_CreepStepsToGo_0 =(CAN_Com_Stack[i].data[0] * 256) + CAN_Com_Stack[i].data[1];	// Specified Motor 0 CCW Creep Rotation in units of 3.3 degrees
							CW_CreepStepsToGo_0  =(CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];	// Specified Motor 0 CW Creep Rotation in units of 3.3 degrees
							CCW_CreepStepsToGo_1 =(CAN_Com_Stack[i].data[4] * 256) + CAN_Com_Stack[i].data[5];	// Specified Motor 1 CCW Creep Rotation in units of 0.1 degrees
							CW_CreepStepsToGo_1  =(CAN_Com_Stack[i].data[6] * 256) + CAN_Com_Stack[i].data[7];	// Specified Motor 1 CW Creep Rotation in units of 0.1 degrees
					}
					break;
				
				case 7:															//execute_move_table
					if(!legacy_test_mode){
						execute_now=1;
					}
					else{
							Sh_Fl_0 = CAN_Com_Stack[i].data[0];
							Sh_Fl_1 = CAN_Com_Stack[i].data[1];
				
							if(CruiseStepsToGo_0 == 0)				Sh_Fl_0 &= 0xB7;		//  This fixes the hang-up which occurred if a Start command was sent with the 
							if(CW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFE;		//  corresponding cruise or creep steps set to zero.  And it does it without adding
							if(CCW_CreepStepsToGo_0 == 0)			Sh_Fl_0 &= 0xFD;		//  anything to the timer ISR.				
							if(CruiseStepsToGo_1 == 0)				Sh_Fl_1 &= 0xB7;
							if(CW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFE;
							if(CCW_CreepStepsToGo_1 == 0)			Sh_Fl_1 &= 0xFD;
	
							Set_Flags = 1;								//  Start
					}
					break;
				
				case 8:															//get_move_table_status		
					data = bit_sum;
					type = 3;													//ready for new move table			
					send_CANmsg(pos_id, 5, data, type);				
					break;
				
				//DATA COMMANDS
				case 9:  //get_temperature
					ADC_Init();
					ADC_StartCnv();
					Delay(10);
					ADC_StopCnv();
					data=ADC_GetCnv();
					send_CANmsg(pos_id, 2, data,0);
					break;
				
				case 10:	//get CAN_address
					data = pos_id;
					send_CANmsg(pos_id, 2, data,0);
					break;
				
				case 11:  //get Firmware Version
					data=FIRMWARE_VR;
					send_CANmsg(pos_id, 1, data,0);
					break;
				
				case 12:  //get device type (fiducial-1 or positioner-0)
					data=device_type;	
					send_CANmsg(pos_id, 1, data,0);
					break;
				
				case 13:  //get movement status
					data=0;
					if((Flags_0) || (Flags_1))	data=1;
					if(Set_Flags || Set_Flags_0 || Set_Flags_1) data=1;
					send_CANmsg(pos_id, 1, data,0);
					break;
				
				case 14:  //get Current Monitor 1 Value
					
					break;
				
				case 15:  //get Current Monitor 2 Value
				
					break;
				
				//FIDUCIAL SETTING	
				case 16:  //set device as fiducial and set duty cycle	
					device_type=CAN_Com_Stack[i].data[0];
					if(device_type){
						duty_cycle= (float) (256*CAN_Com_Stack[i].data[1]+CAN_Com_Stack[i].data[2])/65536;
						period = (256*CAN_Com_Stack[i].data[3]+CAN_Com_Stack[i].data[4])*1000;
						Delay(period);
						duty_cycle= (float) 0;			//turn fiducial off
					}
					
					break;	
					
				//SILICON ID AND FLASH COMMANDS
				case 17:		//read silicon id lower
					ptr = (unsigned long *) 0x1FFFF7E8;		
					data =*ptr;				
					
					ptr = (unsigned long *) 0x1FFFF7EC;		
					data_upper =*ptr;				
					send_CANmsg(pos_id,8, data, data_upper);
					break;
					
				case 18:  //read silicon id upper
					ptr = (unsigned long *) 0x1FFFF7F0;		
					data =*ptr;				
					send_CANmsg(pos_id, 4, data,0);
					break;
				
				case 19:  //read silicon id shortened
					uid = Get_UID_Lower();
					Get_UID_Upper(uid, 1);	
					break;
				
				case 20:	//write CAN_address to flash if previously sent unique id command has set the set_can_id flag
					if(set_can_id){ // if set_can_id flag was set by previously sent unique id check command
						pos_id  = 256*CAN_Com_Stack[i].data[0] + CAN_Com_Stack[i].data[1];
						flash_write(pos_id);
					}
					set_can_id=0;
					Set_Up_CAN_Filters();  //Set up CAN address to be the one that we just wrote to flash
					break;
				
				case 21:		//read memory location where CAN address has been stored
					ptr=(unsigned long *) 0x0801E800;
					data=*ptr;
					data=(unsigned short) data;
					send_CANmsg(pos_id, 2, data,0);
					break;	

				case 22:  //check unique id (lower) and set flag for writing to flash
					ptr = (unsigned long *) 0x1FFFF7E8;		
					data =*ptr;				
				
					ptr = (unsigned long *) 0x1FFFF7EC;		
					data_upper = *ptr;		
					
					//lower 32 bits of received via CAN
					data_rcv = (CAN_Com_Stack[i].data[4]*16777216) + (CAN_Com_Stack[i].data[5] * 65536) + (CAN_Com_Stack[i].data[6] * 256) + CAN_Com_Stack[i].data[7];
					
					//upper 32 bits received via CAN
					data_upper_rcv = (CAN_Com_Stack[i].data[0]*16777216) + (CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
					if(data==data_rcv && data_upper==data_upper_rcv) set_can_id=1;				
					break;
				
				case 23:  //check unique id (lower) and set flag for writing to flash
					ptr = (unsigned long *) 0x1FFFF7F0;		
					data =*ptr;
				
					data_rcv = (CAN_Com_Stack[i].data[0]*16777216) + (CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
					
					if(data==data_rcv && set_can_id==1) set_can_id=1;
					else set_can_id=0;
					break;
				
				case 24:  //check unique id (shortened)
					//lower 32 bits of received via CAN
					uid = Get_UID_Lower();
					uid_upper = Get_UID_Upper(uid, 0);
				
					data_rcv = (CAN_Com_Stack[i].data[4]*16777216) + (CAN_Com_Stack[i].data[5] * 65536) + (CAN_Com_Stack[i].data[6] * 256) + CAN_Com_Stack[i].data[7];
					
					//upper 32 bits received via CAN
					data_upper_rcv = (CAN_Com_Stack[i].data[0]*16777216) + (CAN_Com_Stack[i].data[1] * 65536) + (CAN_Com_Stack[i].data[2] * 256) + CAN_Com_Stack[i].data[3];
				
					if(uid==data_rcv && uid_upper==data_upper_rcv) set_can_id=1;
					break;
				
				case 25: //legacy_test_mode, 1 = legacy_test_mode, 0 = normal operation
					legacy_test_mode = CAN_Com_Stack[i].data[0];
								
				case 26: //firmware_cmd(code,data)?
					
					break;
						
			}	// end switch
		} // end for execution loop
			done=0;
			stack_size=100;
		}//end if done/readsync		
  }	//end while			
} // end main

