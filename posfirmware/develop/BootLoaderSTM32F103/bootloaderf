/*-------------------------------------------------------------------------------
 * Name:    bootloader.c
 * Purpose: Bootloader
 * Author:  PH
 *
 *
 *-----------------------------------------------------------------------------*/

 /*******************************************************
 * 		     Header Files
 ******************************************************/
#include "bootloader.h"

 //  Left from Keil's CAN example  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
volatile uint32_t msTicks;                        /* counts 1ms timeTicks     */
 //  Left from Keil's CAN example  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<


/*******************************************************
 * 		     Global Variables
 *******************************************************/

__IO  uint32_t 		code_size 									=	 4101;						// Size of the whole code in words. Only used to know how many pages to erase. 
const uint32_t		buffer_size									=  5000; //2000; //15360;					 	// Buffer size in words. 5120 words = 20480 Bytes = 20KB. 
__IO  uint32_t		AppliRxBuffer[buffer_size]  =  {0};							// This is the Buffer Variable.
__IO	uint32_t 		statusReg 									=	 0x00000000;

extern CAN_msg       CAN_TxMsg;      // CAN messge for sending
extern CAN_msg       CAN_RxMsg;      // CAN message for receiving    


#define POSITIONER_NR 1004      //  This is the positioner number which is unique for each positioner and is

#define TIMDIV 4000							//  Timer Divide number. This is the number that Timers TIM1 and TIM8 divide by.  So interrupt rate is 
																//	72,000,000/TIMDIV = 18,000 Hz, and the period is 1/18,000 = .0000555555555 seconds 

unsigned int data=0;
unsigned int word_sum=0;							//Received word set bit count
unsigned int error_count=0;					//Flag indicating if sent bit sum and received bit sum match
unsigned int pos_id=65535;						//  This is the can address that all positioners will initially have		


static unsigned short byte_sum[256] = {
//  0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F (<- n)
//  =====================================================
    0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4, // 0n
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, // 1n
	
    1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, // 2n
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // 3n
		1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, // 4n
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // 5n
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // 6n
		3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, // 7n
		1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, // 8n
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // 9n
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // An
		3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, // Bn
		2, 3, 3, 4, 3, 4, 4, 5, 3, 4, 4, 5, 4, 5, 5, 6, // Cn
		3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, // Dn
		3, 4, 4, 5, 4, 5, 5, 6, 4, 5, 5, 6, 5, 6, 6, 7, // En
	
    4, 5, 5, 6, 5, 6, 6, 7, 5, 6, 6, 7, 6, 7, 7, 8, // Fn
};

/* -----------------------------------------------------------------------------------------------------
Assignment of motor phases to I/O pins on PCB P/N BB-0135-v2  --  Note there is no "remapping" of timer outputs
MTR_0 Phase A  --  PA11			TIM1_CH4			Tau0_1
MTR_0 Phase B  --  PA9			TIM1_CH2			Tau0_2
MTR_0 Phase C  --  PA10			TIM1_CH3			Tau0_3
MTR_1 Phase A  --  PC6			TIM8_CH1			Tau1_1
MTR_1 Phase B  --  PC7			TIM8_CH2			Tau1_2
MTR_1 Phase C  --  PC8			TIM8_CH3			Tau1_3
----------------------------------------------------------------------------------------------------- */

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
void can_Init (void) 
{
  CAN_setup ();                                   /* setup CAN Controller     */
//CAN_wrFilter (35, EXTENDED_FORMAT);             /* Enable reception of msgs */  ?????????????????
  CAN_start ();                                   /* start CAN Controller   */
  CAN_waitReady ();   //                          /* wait til tx mbx is empty %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%*/  ??????????????????
}		
//  End of stuff left from Keil's CAN example  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

void flash_PA4(int leng) //LED 1
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	*ptr |= 0x0010;																//  Flash the PA4 LED
	Delay(leng);																	//  This makes a delay of  leng m-sec		
	*ptr &= 0xFFEF;																//  Set PA6 low again
}

void flash_PA5(int leng) //LED 2
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	*ptr |= 0x0020;																//  Flash the PA5 LED
	Delay(leng);																	//  This makes a delay of  leng m-sec		
	*ptr &= 0xFFDF;																//  Set PA6 low again
}

void flash_PA6(int leng) //LED 3
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	*ptr |= 0x0040;																//  Flash the PA6 LED
	Delay(leng);																	//  This makes a delay of  leng m-sec		
	*ptr &= 0xFFBF;																//  Set PA6 low again
}

void flash_PA7(int leng) //LED 2
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	*ptr |= 0x0080;																//  Flash the PA5 LED
	Delay(leng);																	//  This makes a delay of  leng m-sec		
	*ptr &= 0xFF7F;																//  Set PA6 low again
}

void switch_PA4(int led_state) //LED 1
{
	unsigned long *ptr;
	ptr = (unsigned long *) GPIOA_ODR; 
	if(led_state == 1){														//  Flash the PA4 and PA5 LEDs (LED 1 and 2)
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


int readsync_PB2()															//Read sync signal and return its value, returns 1 when button pressed 
{
	
	int status=0;
	
	if((GPIOB->IDR & 0x0004) != 0) {status = 1;}
	else {status = 0;}
	
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
	CAN_TxRdy=1;		
	} //end if(CAN_TxRdy)
}

unsigned short read_flashid()
{
	unsigned long *ptr;
	ptr=(unsigned long *) 0x0801E800;
	data=*ptr;
	data=(unsigned short) data;
	return data;
}


/*----------------------------------------------------------------------------
  Other Functions used in main
 *----------------------------------------------------------------------------*/

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
	*ptr = (pos_id << 11) + 4;								// This is the IDENTIFIER we are looking to accept (the 4 is to set IDE)  (see p.640, 662, 668 for the structure of this)
	
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
 
/*----------------------------------------------------------------------------
  MAIN function
 *----------------------------------------------------------------------------*/
int main (void)
{
	
	unsigned long *ptr;
	uint32_t 			i = 0;
	char 					n = 0;
	uint16_t 			p,packet,currentp = 0;
	uint32_t 			number_of_parts = 0;
	uint64_t 			Txdata;
	uint32_t 			write_operations;
	
	int 					command = 0;						//  This is a number between 0 and 255 which defines the command sent in the CAN message
																				//  It is the LS 8 bits of the IDENTIFIER
	
	ptr = (unsigned long *) RCC_APB2ENR;  				// Turn on clocks to AFIOEN (bit0), IOPA (bit2),
	*ptr |= 0x0000AF3D;									  				// IOPB (bit3), IOPC (bit4), IOPD (bit5), IOPG (bit8),  TIM1 (bit11),  and TIM8 (bit13).

	
	
 	//  Left from Keil's CAN example  >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>		
  SysTick_Config(SystemCoreClock / 1000);       // SysTick 1 msec IRQ       
  can_Init (); 	// initialize CAN interface 
	
	Set_Up_CAN_Filters();
	Set_Up_Standard_GPIO();
	Set_Up_Alt_GPIO();
		
	pos_id = read_flashid();
		
	//if (!readsync_PB2()) jump2Appli();  	// If sync signal is set on startup => jump to main application.
	
	//Wait for CAN message that specifies start mode:  1 = bootloader, 0 = jump to application
	command = 0;
	while(command != 128){
		while(!CAN_RxRdy);					    			// Wait for CAN message 128
		CAN_RxRdy = 0;
		command = CAN_RxMsg.id &= 0xFF;
		if (command == 128) {
			if (CAN_RxMsg.data[0] != 1) jump2Appli();
	}
  }
	
	
	while(!CAN_RxRdy);					    			// Wait for CAN message 129
	CAN_RxRdy = 0;
	command = CAN_RxMsg.id &= 0xFF;
	
	if (command == 129) {
		code_size = 0;
		code_size |= CAN_RxMsg.data[3];
		code_size |= CAN_RxMsg.data[2] << 8;
		code_size |= CAN_RxMsg.data[1] << 16;
		code_size |= CAN_RxMsg.data[0] << 24;
		
	}						
			
	while(!CAN_RxRdy);					    			// Wait for CAN message 130
	CAN_RxRdy = 0;
	command = CAN_RxMsg.id &= 0xFF;
	
	if (command == 130) {
		number_of_parts = 0;
		number_of_parts |= CAN_RxMsg.data[3];
		number_of_parts |= CAN_RxMsg.data[2] << 8;
		number_of_parts |= CAN_RxMsg.data[1] << 16;
		number_of_parts |= CAN_RxMsg.data[0] << 24;
		
	}			
	
	// Erase Flash pages form Page 62 to Page 62 + code size in bytes 
	EraseFlash:
	error_count = 0;
	//send_CANmsg(pos_id, 4, statusReg, 0);
	EraseFlashForApplication(APPLI_START_ADDR, APPLI_START_ADDR + 4*code_size);
	
	for (n=0; n<number_of_parts; n++){
		ReadyForPartN:
		
		for (p=0; p<(buffer_size*4); p++){				// for all packets in part n
			
			send_CANmsg(pos_id, 1, n+1, 0);
			
			while(!CAN_RxRdy);					    		// Wait for CAN message 130
			CAN_RxRdy = 0;
			command = CAN_RxMsg.id &= 0xFF;
			if (command != 132) error_count +=1;
			if (CAN_RxMsg.data[0] != (n+1)) error_count +=1;
			packet = 0;
			packet |= CAN_RxMsg.data[2];
			packet |= CAN_RxMsg.data[1] << 8;
			if (packet != p) error_count +=1;
			send_CANmsg(80, 4, p, 0);
			
			AppliRxBuffer[p] = 0;
			send_CANmsg(80, 4, p, 0);
			AppliRxBuffer[p] |= CAN_RxMsg.data[3];
			AppliRxBuffer[p] |= CAN_RxMsg.data[4] << 8;
			AppliRxBuffer[p] |= CAN_RxMsg.data[5] << 16;
			AppliRxBuffer[p] |= CAN_RxMsg.data[6] << 24;
			
			
			word_sum = byte_sum[CAN_RxMsg.data[3]] + byte_sum[CAN_RxMsg.data[4]] + byte_sum[CAN_RxMsg.data[5]] + byte_sum[CAN_RxMsg.data[6]];
			//send_CANmsg(81, 4, p, 0);
			if (word_sum != CAN_RxMsg.data[7]) error_count +=1;
			if (currentp == (code_size*4-1)) p = (4*buffer_size);							//leave loop, no more packets expected
			send_CANmsg(pos_id, 8, n, p);
			send_CANmsg(pos_id, 8, currentp, code_size*4);
			send_CANmsg(pos_id, 4, error_count, 0);
			currentp += 1;
		} //end for buffer_size. Part n is now complete
		
		
		//write buffer to flash and verify number of write operations
		write_operations = WriteRxBuffer(APPLI_START_ADDR + n*4*buffer_size);   //changed code_size to buffer size
		send_CANmsg(1799, 8, write_operations, AppliRxBuffer[buffer_size-1]);
		if (write_operations != buffer_size) error_count +=1;
		
		
		//for (i=0; i < buffer_size; i++) AppliRxBuffer[i]=0;										//Set all buffer elements to 0
	} 
	
	//Wait for final verification command from PC
	command = 0;
	while (command != 131) {
	while (!CAN_RxRdy);
	CAN_RxRdy = 0;
	command = CAN_RxMsg.id &= 0xFF;
	
	if (command == 131){
	
		if(error_count == 0){
			send_CANmsg(pos_id, 1, 1, 0);
			Delay(1);
			jump2Appli();
		}
		else{
			send_CANmsg(pos_id, 1, 0, 0);
			goto EraseFlash;
		}	
	}
}	
} // end main

