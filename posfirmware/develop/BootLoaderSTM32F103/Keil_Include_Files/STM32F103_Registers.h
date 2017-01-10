/*----------------------------------------------------------------------------
 * Name:    STM32F103_Registers.h
 * Purpose: This gives addresses for the registers in the STM32F103 we are using
 * 					or might use later.
 * 2012-12-22
 *----------------------------------------------------------------------------*/
#define AFIO_EVCR	  	0x40010000		//  This selects which Port pin 'EVENTOUT" is connected to; (see page 178)
#define AFIO_MAPR   	0x40010004		//  Specifies "Remapping" of alternative IO functions.  Used on TIM2 and TIM3
																		//	For bits 9:8   TIM2_REMAP = 10 Gives: (CH1/ETR/PA0, CH2/PA1, CH3/PB10, CH4/PB11)
																		//	For bits 11:10 TIM3_REMAP = 10 Gives: (CH1/PB4, CH2/PB5, CH3/PB0, CH4/PB1)
																		//  I.e. want: AFIO_MAPR = 0xSSSSSASS
																		
//  The following 4 registers map the EXTI0 thru 18 to GPIO pins as follows:  (see page 185)
//  EXTIn always connects to pin n of a GPIO port.  The registers below determine which port each connects to.
//  I assume the pins used have to be programmed as inputs
#define AFIO_EXTICR1 	0x40010008		//  Groups of 4 bits handle EXTI0 thru 3, with 0000>PA; 0001>PB; 0010>PC; 0011>PD; 0100>PE; 0101>PF; and 0110>PG
#define AFIO_EXTICR2 	0x4001000C		//  Same but for EXTI4 thru 7
#define AFIO_EXTICR3 	0x40010010		//  Same but for EXTI8 thru 11  
#define AFIO_EXTICR4 	0x40010014		//  Same but for EXTI12 thru 15     (see page 200 for EXTI16, 17, and 18)  															
																		
//  For EXTI registers, bits 0 through 18 correspond to EXTI0 through 18																		
#define EXTI_IMR			0x40010400		//	If '1', interrupt request from that line is masked													
#define EXTI_EMR			0x40010404		//  If '0', event request from that line is masked  >>>>>>>What is an Event Request??<<<<<<<<<<<<<<<<<<<<<<<<<<<
#define EXTI_RTSR			0x40010408		//  If '1', rising trigger for that line is enabled
#define EXTI_FTSR			0x4001040C		//  If '1', falling trigger for that line is enabled
#define EXTI_SWIER		0x40010410		//  Writing 0->1 sets the corresponding bit in EXTI_PR; if IMR and EMR are both enabled, this gives an interrupt
#define EXTI_PR				0x40010414		//  Bits are set when edge occurs on line;  this is rc_w1; 

#define GPIOA_CRL   	0x40010800		//  Defines register locations for GPIO port A
#define GPIOA_CRH			0x40010804
#define GPIOA_IDR			0x40010808
#define GPIOA_ODR  		0x4001080C
#define GPIOA_BSRR 		0x40010810
#define GPIOA_BRR  		0x40010814
#define GPIOA_LCKR 		0x40010818 

#define GPIOB_CRL  		0x40010C00		//  Defines register locations for GPIO port B
#define GPIOB_CRH   	0x40010C04
#define GPIOB_IDR   	0x40010C08
#define GPIOB_ODR   	0x40010C0C
#define GPIOB_BSRR  	0x40010C10
#define GPIOB_BRR   	0x40010C14
#define GPIOB_LCKR  	0x40010C18 

#define GPIOC_CRL   	0x40011000		//  Defines register locations for GPIO port C
#define GPIOC_CRH   	0x40011004
#define GPIOC_IDR   	0x40011008
#define GPIOC_ODR   	0x4001100C
#define GPIOC_BSRR  	0x40011010
#define GPIOC_BRR   	0x40011014
#define GPIOC_LCKR  	0x40011018

#define GPIOD_CRL   	0x40011400		//  Defines register locations for GPIO port D
#define GPIOD_CRH   	0x40011404
#define GPIOD_IDR   	0x40011408
#define GPIOD_ODR   	0x4001140C
#define GPIOD_BSRR  	0x40011410
#define GPIOD_BRR   	0x40011414
#define GPIOD_LCKR  	0x40011418

#define GPIOG_CRL   	0x40012000		//  Defines register locations for GPIO port G
#define GPIOG_CRH   	0x40012004
#define GPIOG_IDR   	0x40012008
#define GPIOG_ODR   	0x4001200C
#define GPIOG_BSRR  	0x40012010
#define GPIOG_BRR   	0x40012014
#define GPIOG_LCKR  	0x40012018

#define TIM1_CR1			0x40012C00		//  Set this to 0x85,  but I'm not sure about bit 2
#define TIM1_CR2			0x40012C04		//  This is left all zeros?
#define TIM1_SMCR			0x40012C08		//  Leave this at all zeros?	
#define TIM1_DIER			0x40012C0C		//  Set these to '0x1'?
#define TIM1_SR				0x40012C10		//  These are rc_w0;  bits 1,2,3,4 are compare flags; bit 0 is Update Interrupt Flag
#define TIM1_EGR			0x40012C14		//  Not clear;  maybe bit 0 = 1 to have auto update of counter?
#define TIM1_CCMR1		0x40012C18		//  Set to 0X6868  to set up for compare CH2 and CH1
#define TIM1_CCMR2		0x40012C1C		//  Set to 0X6868  to set up for compare CH4 and CH3
#define TIM1_CCER			0x40012C20		//  Set to 0X1111  to make all compare outputs active high and connected to
#define TIM1_CNT			0x40012C24		//  This is the actual timer's counter
#define TIM1_PSC			0x40012C28		//  This is the pre-scale counter; set to zero for divide by 1
#define TIM1_ARR			0x40012C2C		//  This is the auto reload register.  I will set it to 10*360 = 3,600
#define TIM1_RCR			0x40012C30
#define TIM1_CCR1			0x40012C34		//  This is the compare register for channel 1
#define TIM1_CCR2			0x40012C38		//  This is the compare register for channel 2	
#define TIM1_CCR3			0x40012C3C		//  This is the compare register for channel 3	
#define TIM1_CCR4			0x40012C40		//  This is the compare register for channel 4	
#define TIM1_BDTR			0x40012C44		//  
#define TIM1_DCR			0x40012C48		//  	
#define TIM1_DMAR			0x40012C4C		//  

#define TIM2_CR1			0x40000000		//  Set this to 0x85,  but I'm not sure about bit 2
#define TIM2_CR2			0x40000004		//  This is left all zeros?
#define TIM2_SMCR			0x40000008		//  Leave this at all zeros?
#define TIM2_DIER			0x4000000C		//  Set these to '0x1'?
#define TIM2_SR				0x40000010		//  These are rc_w0;  bits 1,2,3,4 are compare flags; bit 0 is Update flag. Don't set them
#define TIM2_EGR			0x40000014		//  Not clear;  maybe bit 0 = 1 to have auto update of counter?
#define TIM2_CCMR1		0x40000018		//  Set to 0X6868  to set up for compare CH2 and CH1
#define TIM2_CCMR2		0x4000001C		//  Set to 0X6868  to set up for compare CH4 and CH3
#define TIM2_CCER			0x40000020		//  Set to 0X1111  to make all compare outputs active high and connected to the output pin
#define TIM2_CNT			0x40000024		//  This is the actual timer's counter
#define TIM2_PSC			0x40000028		//  This is the pre-scale counter; set to zero for divide by 1
#define TIM2_ARR			0x4000002C		//  This is the auto reload register.  I will set it to 10*360 = 3,600 to allow for 10 values of motor current, and rotation steps of 1 degree
#define TIM2_CCR1			0x40000034		//  This is the compare register for channel 1
#define TIM2_CCR2			0x40000038		//  This is the compare register for channel 2
#define TIM2_CCR3			0x4000003C		//  This is the compare register for channel 3
#define TIM2_CCR4			0x40000040		//  This is the compare register for channel 4

#define TIM3_CR1			0x40000400
#define TIM3_CR2			0x40000404
#define TIM3_SMCR			0x40000408
#define TIM3_DIER			0x4000040C		//  These are rc_w0;  bits 1,2,3,4 are compare flags; bit 0 is Update flag. Don't set them
#define TIM3_SR				0x40000410		// 
#define TIM3_EGR			0x40000414
#define TIM3_CCMR1		0x40000418
#define TIM3_CCMR2		0x4000041C
#define TIM3_CCER			0x40000420		// 
#define TIM3_CNT			0x40000424
#define TIM3_PSC			0x40000428		//  This is the auto reload register.  I will set it to 10*360 = 3,600 to allow for 10 values of motor current, and rotation steps of 1 degree
#define TIM3_ARR			0x4000042C		//  This is the compare register for channel 1
#define TIM3_CCR1			0x40000434		
#define TIM3_CCR2			0x40000438		
#define TIM3_CCR3			0x4000043C		
#define TIM3_CCR4			0x40000440	

#define TIM8_CR1			0x40013400		//  Set this to 0x85,  but I'm not sure about bit 2
#define TIM8_CR2			0x40013404		//  This is left all zeros?
#define TIM8_SMCR			0x40013408		//  Leave this at all zeros?	
#define TIM8_DIER			0x4001340C		//  Set these to '0x1'?
#define TIM8_SR				0x40013410		//  These are rc_w0;  bits 1,2,3,4 are compare flags; bit 0 is Update flag
#define TIM8_EGR			0x40013414		//  Not clear;  maybe bit 0 = 1 to have auto update of counter?
#define TIM8_CCMR1		0x40013418		//  Set to 0X6868  to set up for compare CH2 and CH1
#define TIM8_CCMR2		0x4001341C		//  Set to 0X6868  to set up for compare CH4 and CH3
#define TIM8_CCER			0x40013420		//  Set to 0X1111  to make all compare outputs active high and connected to
#define TIM8_CNT			0x40013424		//  This is the actual timer's counter
#define TIM8_PSC			0x40013428		//  This is the pre-scale counter; set to zero for divide by 1
#define TIM8_ARR			0x4001342C		//  This is the auto reload register.  I will set it to 10*360 = 3,600
#define TIM8_RCR			0x40013430
#define TIM8_CCR1			0x40013434		//  This is the compare register for channel 1
#define TIM8_CCR2			0x40013438		//  This is the compare register for channel 2	
#define TIM8_CCR3			0x4001343C		//  This is the compare register for channel 3	
#define TIM8_CCR4			0x40013440		//  This is the compare register for channel 4	
#define TIM8_BDTR			0x40013444		//  
#define TIM8_DCR			0x40013448		//  	
#define TIM8_DMAR			0x4001344C		//  

#define RCC_CR				0x40021000	  //  Defines register locations for Clock Enables, Etc.
#define RCC_CFGR			0x40021004	
#define RCC_CIR				0x40021008	
#define RCC_APB2RSTR	0x4002100C	
#define RCC_APB1RSTR	0x40021010	
#define RCC_AHBENR		0x40021014	
#define RCC_APB2ENR		0x40021018		//  Set bit 0 to enable the clock for AFIOEN (Alt Fcn Enable);	TIM8 -- bit 13; TIM1 -- bit 11; GPIOA -- bit 2; GPIOB -- bit 3; GPIOC -- bit 4
#define RCC_APB1ENR		0x4002101C		//  Set bit 0 to enable the clock for TIM2; TIM3 -- bit 1; TIM4 -- bit 2; TIM5 -- bit 3; TIM6 -- bit 4; TIM7 -- bit5	
																		//  Set bit 25 to enable CAN
#define RCC_BDCR			0x40021020
#define RCC_CSR				0x40021024


#define CAN_MCR				0x40006400		//  Master Control Register. Bit0 (INRQ) is request to go into Initiallation Mode.  (se p. 648)
#define CAN_MSR				0x40006404		//  Master Status Register. Bit0 (INAK)acknowledges a request to go into Initialization Mode
#define CAN_TSR				0x40006408		//  Transmit status register  (see page 651)
#define CAN_RF0R			0x4000640C		//  Write bit5 = 1 to release FIFO output; bits 1-0 show how many messages in receive FIFO
#define CAN_RF1R			0x40006410		//  
#define CAN_IER				0x40006414		//  Interrupt enables
#define CAN_ESR				0x40006418		//  Receive error information
#define CAN_BTR				0x4000641C		//  Sets up Silent Mode, Loop Back, and bit rate stuff
#define CAN_TI0R			0x40006580
#define CAN_TI1R			0x40006590
#define CAN_TI2R			0x400065A0
#define CAN_TDT0R			0x40006584
#define CAN_TDT1R			0x40006594
#define CAN_TDT2R			0x400065A4
#define CAN_TDL0R			0x40006588
#define CAN_TDL1R			0x40006598
#define CAN_TDL2R			0x400065A8
#define CAN_TDH0R			0x4000658C
#define CAN_TDH1R			0x4000659C
#define CAN_TDH2R			0x400065AC
#define CAN_RI0R			0x400065B0		//  STID/EXID;  EXID;  IDE;  RTR
#define CAN_RI1R			0x400065C0		//  
#define CAN_RDT0R			0x400065B4		//  Time, Match Filter, and data length  (see p. 663)
#define CAN_RDT1R			0x400065C4		//  
#define CAN_RDL0R			0x400065B8		//  Data bytes 3 -> 0
#define CAN_RDL1R			0x400065C8		//  
#define CAN_RDH0R			0x400065BC		//  Data bytes 7 -> 4
#define CAN_RDH1R			0x400065CC		//  
#define CAN_FMR				0x40006600		// Only the LSB is active.  '0' is active mode;  '1' is initialization mode.
#define CAN_FM1R			0x40006604		// Only the lower order 14 bits are active.  A '1' sets Identifier List Mode.  (else Mask Mode)
#define CAN_FS1R			0x4000660C		// Only the lower order 14 bits are active.  A '1' means a single 32-bit scale configuration  (see p. 640)
#define CAN_FFA1R			0x40006614		// Only the lower order 14 bits are active.  A '1' assigns the filter to FIFO 1
#define CAN_FA1R			0x4000661C		// Only the lower order 14 bits are active.   A '1' activates the corresponding filter.   
#define CAN_F0R1			0x40006640		// 
#define CAN_F0R2			0x40006644
#define CAN_F1R1			0x40006648
#define CAN_F1R2			0x4000664C
#define CAN_F2R1			0x40006450
#define CAN_F2R2			0x40006454
#define CAN_F3R1			0x40006458
#define CAN_F3R2			0x4000645C
#define CAN_F4R1			0x40006460
#define CAN_F4R2			0x40006464
#define CAN_F5R1			0x40006468
#define CAN_F5R2			0x4000646C
#define CAN_F6R1			0x40006470
#define CAN_F6R2			0x40006474
#define CAN_F7R1			0x40006478
#define CAN_F7R2			0x4000647C
#define CAN_F8R1			0x40006480
#define CAN_F8R2			0x40006484
#define CAN_F9R1			0x40006488
#define CAN_F9R2			0x4000648C
#define CAN_F10R1			0x40006490
#define CAN_F10R2			0x40006494
#define CAN_F11R1			0x40006498
#define CAN_F11R2			0x4000649C
#define CAN_F12R1			0x400064A0
#define CAN_F12R2			0x400064A4
#define CAN_F13R1			0x400064A8
#define CAN_F13R2			0x400064AC

  










