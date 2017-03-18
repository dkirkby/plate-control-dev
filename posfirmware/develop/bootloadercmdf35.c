/*-------------------------------------------------------------------------------
 * Name:    bootloader.c
 * Purpose: Bootloader
 * Author:  PH, IG, with comments and modifications by hdh
 *
 * bootloadercmdf35.c   2017-03-15    This removes the LED functionality used for troubleshooting, adds a structure for sharing the bootloader version with the application, 
 *                                    and bootloader no longer automatically sends out version # but only does so if command 128 is sent without the bootloader mode sequence.  Added
 *                                    call to CAN_waitReady() at the beginning of jump2Appli().  This lets us wait until the CAN transmit mailbox is empty before jumping to the 
 *                                    application.  Empty values are no longer written from the buffer to flash.
 *
 * bootloadercmdf34.c   2017-03-13    This adds a bootloader firmware version which is included in a CAN message sent by the bootloader code on reset
 *
 * bootloadercmdf33.c   2017-03-10    This uses Command 128 to select bootloader mode, rather than using the sync line. If CAN message 128 is received with the 8 data bytes
 *                                    as {77, 46, 69, 46, 76, 101, 118, 105} then it goes into bootloader mode. Otherwise it branches to the fipos firmware. 
 *                                    If the command is not received within 2 seconds, or any other command is received, it also branches to the firmware.
 * bootloadersyncf32.c  2017-03-02    Modifications by hdh; tried to remove unused stuff.  Brought code from custom_flash_functions.c into this file to make it easier to read
 *                                    This version still uses the sync line to select boot mode.  f33 will be a version which uses a command instead.
 * bootloadersyncf31.c  2017-01-10    Taken from ZIP file source:code/focalplane/plate_control/trunk/posfirmware/develop/BootLoaderSTM32F103.zip on SVN on  2017-02-16
 *                                    Last change on this file was 7623, checked in by igershko, at 2017-02-07T06:51:56-08:00
 *-----------------------------------------------------------------------------*/
 																									
 /*******************************************************   // Note:  The locked Device files (e.g.misc.c and stm32f10x_flash.c) can be found in a typical Keil installation at:
 *           Header Files                                   // C:\Program_Files\ARM\PACK\Keil\STM32F1xx_DFP\2.1.0\Device\StdPeriph_Driver\src\
 ******************************************************/
 #include "bootloader.h"                                    // Use: Configure Flash Tools -> C/C++ -> USE_STDPERIPH_DRIVER (in the Preprocessor Symbols Define field)

/*******************************************************
 *          Global Variables
 *******************************************************/
#define BOOTLOADERVR_MJR   3                                // Put the firmware version here at the top of the source
#define BOOTLOADERVR_MNR	 5                                // If specified by command 128, the bootloader will send a CAN message with ID = pos_id + 0x10000000, and 8 bytes of data: 'B', 'o', 'o', 't', 'F', 'W', 0x03, 0x05
#define BroadCast_ID       20000                            // This ID is installed permanently into the bootloader as part of the CAN filters setup (See ~line 195)

volatile uint32_t msTicks;                                  // Counts 1ms timeTicks.  An interrupt set up by the STMicro start routine increments msTicks every milli-second.  
__IO  uint32_t  code_size                  = 4101;          // Size of the code to be downloaded in words.  Used to know how many pages to erase. This gets set to actual value by CAN message 129.
const uint32_t  buffer_size                = 4000;          // Buffer size in words. 5120 words = 20480 Bytes = 20KB. 4000 words = 16000 KB. 
__IO  uint32_t  AppliRxBuffer[buffer_size] = {0};           // This is the buffer where the downloaded code is stored before being written into the flash memory

extern CAN_msg   CAN_TxMsg;                                 // CAN messge for sending defined in CAN.c
extern CAN_msg   CAN_RxMsg;                                 // CAN message for receiving defined in CAN.c 

unsigned int word_sum = 0;                                  // Received word set bit count  
                                                            // So all positioners will respond to CAN messages with this value in bits 11 through 26 of the message ID
unsigned int pos_id=0;                                      // pos_id is the individual ID of a particular positioner. The bootloader software reads the value of pos_id from
                                                            // the first two bytes of page 61 in the flash memory (i.e. memory location 0x0801E800).
static unsigned short byte_sum[256] = {                     // When the bootloader and firmware are first installed, unused flash memory is set to 0xFFFFFFFF,
// 0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F 	(<- n)  // so all positioners will initially respond to CAN messages sent to ID 65,535.
// =======================================                  // Prior to test or installation of the positioner, it will be programmed with a unique ID by writing 
   0, 1, 1, 2, 1, 2, 2, 3, 1, 2, 2, 3, 2, 3, 3, 4, // 0n    // two bytes into flash memory at 0x0801E800.  It is planned that this ID will be the same as the hardware
   1, 2, 2, 3, 2, 3, 3, 4, 2, 3, 3, 4, 3, 4, 4, 5, // 1n    // serial number assigned to the positioner at manufacture, and written by hand on the circuit board
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

typedef struct _LOADER_DATA{                                // Structure for sharing bootloader_version between bootloader and main application, identical structure is defined in application
    uint32_t bootloadervr_mjr;
	  uint32_t bootloadervr_mnr;
}LOADER_DATA;

LOADER_DATA *LoaderData = (LOADER_DATA *)0x20004C00;       // Structure stored at RAM address and shared by bootloader and main application, for passing data between the two

/*----------------------------------------------------------------------------
  SysTick_Handler
 *----------------------------------------------------------------------------*/
void SysTick_Handler(void)
{
  msTicks++;                                               // increment counter necessary in Delay()
}

/*------------------------------------------------------
  delays number of tick Systicks (happens every 1 ms)
 *------------------------------------------------------*/
void Delay (uint32_t dlyTicks)
{
  uint32_t curTicks = msTicks;
  while ((msTicks - curTicks) < dlyTicks);                 // An interrupt set up by the STMicro start routine increments msTicks every milli-second
}

/*------------------------------------------------------
   Custom CAN functions used in main
 *------------------------------------------------------*/
void can_Init (void) 
{
  CAN_setup ();                                            // setup CAN Controller -- These functions are all in CAN.c 
  CAN_start ();                                            // start CAN Controller
  CAN_waitReady ();                                        // wait until Tx mailbox is empty
}

void send_CANmsg(int can_add, int length, int data_lower, int data_upper)	
{                                                          // Function for sending CAN messages
  CAN_waitReady( );                                        // This was can_init();  CAN_waitReady() seems to work just fine <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
  CAN_TxRdy=0;                                             // Reset CAN_TxRdy	
  CAN_TxMsg.id=can_add;
  CAN_TxMsg.len=length;
  CAN_TxMsg.format = EXTENDED_FORMAT;                      // STANDARD_FORMAT=0,    EXTENDED_FORMAT=1
  CAN_TxMsg.type = DATA_FRAME;                             // DATA_FRAME=0,         REMOTE_FRAME=1
  CAN_TxMsg.data[0] =  data_lower        & 0x000000FF;     // Write data_lower into CAN data bytes 0-3
  CAN_TxMsg.data[1] = (data_lower >> 8)  & 0x000000FF;
  CAN_TxMsg.data[2] = (data_lower >> 16) & 0x000000FF;
  CAN_TxMsg.data[3] = (data_lower >> 24) & 0x000000FF;
  CAN_TxMsg.data[4] =  data_upper        & 0x000000FF;     // Write data_upper into CAN data bytes 4-7
  CAN_TxMsg.data[5] = (data_upper >> 8)  & 0x000000FF;
  CAN_TxMsg.data[6] = (data_upper >> 16) & 0x000000FF;
  CAN_TxMsg.data[7] = (data_upper >> 24) & 0x000000FF;	
  CAN_wrMsg(&CAN_TxMsg);                                   // Transmit message													  			
  CAN_TxRdy=1; 
}

/*--------------------------------------------
  Custom Flash functions used in main
 *-------------------------------------------*/
void EraseFlashForApplication(uint32_t Start_Address, uint32_t End_Address)  
{                                                          // Given a Start_Address and an End_Address, both at an arbitrary location in the Flash Memory, this function will erase
  uint32_t  StartPage = 0;                                 // the area from Start_Address to End_Address, including the entire page containing the Start_Address and that of the 
  uint32_t    EndPage = 0;                                 // End_Address.  (Because flash memory can be erased only in complete 2048 byte pages.)
  uint32_t          i = 0;
	
  FLASH_Unlock();                                          // This writes the two values FLASH_KEY1 and FLASH_KEY2 (called KEY1 and KEY2 in PM0075) to the memory address FLASH_KEYR
  FLASH_ClearFlag(FLASH_FLAG_EOP |  FLASH_FLAG_WRPRTERR | FLASH_FLAG_PGERR | FLASH_FLAG_BSY); // This function clears all 4 bits in FLASH_SR by writing '1' to them. Only these 4 bits are used in FLASH_SR.
  StartPage = Start_Address & 0xFFFFF800;                  // Mask off the 11 LS Bits so as to give the address of the beginning of the 2048 byte page in the flash memory.
  EndPage 	= End_Address   & 0xFFFFF800;                  // Do this because Flash Memory can be erased only in full 2048 byte pages
	
  for(i=StartPage; i<=EndPage; i+=2048)                    // The function FLASH_ErasePage(Address) requires the full address in memory of the beginning of the page to be erased,
  {                                                        // and then erases the  entire 2048 byte page.  That is why i is incremented by 2048.	
    if (FLASH_ErasePage(i) != FLASH_COMPLETE)	while (1); // Stop and loop here if a flash page erase does not complete.  Have to cycle power to get out of this. <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
  }
  FLASH_Lock();                                            // Disable writing to flash memory again
}

uint32_t WriteRxBuffer(uint32_t Start_Address, uint16_t  currentp)             // This function writes buffer_size number of words starting from AppliRxBuffer[0]  to Start_Address in Flash Memory
{																										  
  uint32_t  WriteOperationCount = 0;                       // It returns WriteOperationCount which is the number of Flash word writes which were performed
  static uint32_t  CurrentAddress      = 0;
  uint32_t         i                   = 0;
	
  CurrentAddress = Start_Address;
  FLASH_Unlock();
  FLASH_ClearFlag(FLASH_FLAG_EOP |  FLASH_FLAG_WRPRTERR | FLASH_FLAG_PGERR | FLASH_FLAG_BSY); // Note that FLASH_FLAG_OPTERR doesn't belong here. It is bit 1 in a different register.
  while (i < currentp)
  {
    if (FLASH_ProgramWord(CurrentAddress, AppliRxBuffer[i]) == FLASH_COMPLETE)
    {
      CurrentAddress = CurrentAddress + 4;                 // Increment the address by one word
      i++;
      WriteOperationCount++;
    }
    else   while(1);                                       // Stop and loop here because Write to Flash did not complete.  Have to cycle power to get out of this.  <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
  }
  FLASH_Lock();                                            // Lock Flash against writing again
  return WriteOperationCount;
}

void jump2Appli()                                          // This jumps to the application (fipos)
{
  CAN_waitReady();                                         // Wait until the CAN transmit mailbox is empty before jumping the application (otherwise some messages may not get sent)
  __set_MSP( *(__IO uint32_t*) APPLI_START_ADDR );         // Initialize the Stack Pointer to the memory location whose address is stored at APPLI_START_ADDR which is currently set to page 62 (0x0801F000) in bootloader.h)
  ((pFunction)*(__IO uint32_t*) (APPLI_START_ADDR + 4))(); // Then run the fipos code which starts at the address stored at APPLI_START_ADDR + 4																
}                                                          // Note: A pFunction seems to be an ARM unique thing?  It appears to branch to the memory address stored at the operand? <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

/*------------------------------------------------------
  Other Functions used in main
 *------------------------------------------------------*/
void Set_Up_Standard_GPIO(void)                            // Sets up the GPIOB pins PB2 (used for sync and to trigger the bootloader), and PB5 (used as motor current enable)
{
  *(unsigned long *) GPIOB_CRH &= 0x000000FF;              // Set PB10 as push/pull output with 10mHz speed; need this to receive CAN messages because PB10 is connected to RS (sleep mode if '1') on the CAN interface IC
  *(unsigned long *) GPIOB_CRH |= 0x88888100;              // PB11-PB15 are not connected on PCB, so set to input with pull up/down.  PB8 and PB9 are used by CAN
  *(unsigned long *) GPIOB_ODR  = 0x00000000;              // Sets all GPIOB outputs including PB5 and PB10 to 0.  A '0' in ODR makes any input with a pull up/down to be a pull down.
  *(unsigned long *) GPIOB_CRL  = 0x88888888;              // Sets GPIOB bits 0-7 to input mode with a pull up or down 
  *(unsigned long *) GPIOB_CRL &= 0xFF0FFFFF;              // Then sets PB5 to be an output because it is connected to the motor switch enable line.
  *(unsigned long *) GPIOB_CRL |= 0x00100000;              // The '1' for PB5 makes it a 10mHz output. This is connected to the switch enable, and since it is low, turns off all motor switches
}

void Set_Up_CAN_Filters(void)
{
// Set up a filter which accepts only CAN messages with ID = pos_id, but with any type code -- The FINIT bit has to be set = '1' to allow change of CAN_FA1R
  *(unsigned long *) CAN_FMR  |= 0x00000001;               // The FINIT bit has to be set = '1' to allow change of CAN_FA1R
  *(unsigned long *) CAN_FA1R |= 0x00000003;               // Selects which filters are active,  This enables filter 0 and 1 (out of the total of 13 available)
  *(unsigned long *) CAN_FFA1R &= 0xFFFFFFFC;              // Assigns Filters 0 and 1 to FIFO 0 (i.e. messages which get thru these filters will end up in FIFO 0 as opposed to FIFO 1)
  *(unsigned long *) CAN_FS1R |= 0x00000003;               // Sets Filters 0 and 1  to be a single 32 bit register which covers all 29 bits of the ID plus IDE and RTR
  *(unsigned long *) CAN_FM1R &= 0xFFFFFFFC;               // Sets Filters 0 and 1 for Identifier Mask Mode, i.e. FxR2 specifies which bits are checked, and FxR1 specifies what they should be
	
// Set up two filters with Identifier and Mask, so as to accept messages for either pos_id or BroadCast_ID (see p. 640, 662 and 668 in RM0008 for how the CAN filters work)
  pos_id = (unsigned short) *(unsigned long *) 0x0801E800; // Get the Positioner ID as the contents of first two bytes of page 61 in flash
  *(unsigned long *) CAN_F0R1 = ((uint32_t) pos_id << 11) + 4;// Set up filter 0 to accept only the positioner specified by the specified pos_id, with IDE='1' (which says it is a 29 bit ID)  (FxR1 is the ID)
                                                           // Cast pos_id as a long to avoid losing the MSB's when it is shifted
  *(unsigned long *) CAN_F0R2 = 0xFFFFF806;                // F0R2 is the MASK for filter 0. A mask bit of '0' accepts either 1 or 0 in that bit; we have 1's for the Positioner ID and for IDE and RTR 
  *(unsigned long *) CAN_F1R1 = (BroadCast_ID << 11) + 4;  // Set up filter 1 to accept BroadCast_ID (which is currently 0x00004E20),  along with IDE='1' and RTR='0'
  *(unsigned long *) CAN_F1R2 = 0xFFFFF806;                // F1R2 is the MASK for filter 1. A mask bit of '0' accepts either 1 or 0 in that bit; we have 1's for the Positioner ID and for IDE and RTR   
  *(unsigned long *) CAN_FMR &= 0xFFFFFFFE;                // Finally activiate the filters again: Put the FINIT bit low again to activate Filter 0 and filter 1
}                                                          // So overall, the filters are set up so that a given positioner will accept CAN messages addressed to its pos_id, or to BroadCast_ID

/*------------------------------------------------------ 
                   MAIN function
 *------------------------------------------------------*/
int main (void)
{
  char      n = 0;                                         // n is used to keep track of which "Part" of the application code is being downloaded. A Part is one buffer worth of application code.
  uint16_t  p = 0;                                         // p keeps track of which packet (= one 32 bit word) within the Part is being downloaded
  uint16_t  packet          = 0;                           // packet is a variable which is written into data[0] and data[1] of the command 132 messages which tells which packet it is in the Part.  (packet should = p)
  uint16_t  currentp        = 0;                           // currentp is the packet number over the entire application code including all Parts
  uint32_t  number_of_parts = 0;                           // number_of_parts is sent by command 129, and tells the number of Parts (each of buffer_size in length) are required for the full application code
  uint32_t  write_operations;                              // write_operations is the number of words written to Flash Memory when a full buffer is written. It should = buffer_size.
  int       command         = 0;                           //  This is a number between 0 and 255 which defines the command sent in the CAN message -- It is the LS 8 bits of the IDENTIFIER in the CAN message
  unsigned int ErrCnt[5]    = {0, 0, 0, 0, 0};             // Keep count of various kinds of error while writing to the flash memory<<<<<<<<<<<<<<<<<<<<<<<<<<<
	
  *((unsigned long *) RCC_APB2ENR) |= 0x0000000C;          // Turn on clocks for IOPB (bit3) and IOPA (bit2)

  SysTick_Config(SystemCoreClock / 1000);                  // SysTick 1 msec IRQ       
  can_Init ();                                             // Initialize the CAN interface 
  Set_Up_CAN_Filters();                                    // Sets up two filters: filter 0 passes messages addressed to this positioner's pos_id, and filter 1 passes messages addressed to BroadCast_ID
  Set_Up_Standard_GPIO();                                  // Sets up PB5 a 10mHz output set low (to disable motor switches).	Also sets PB10 as an output set low to enable the CAN chip.					
  pos_id = (unsigned short) *(unsigned long *) ADDR_FLASH_PAGE_61; //Read 16 bits at start of page 61 of flash memory (address = 0x0801E800).  This reads the Positioner ID from the flash memory
  LoaderData->bootloadervr_mjr = BOOTLOADERVR_MJR;         // Set bootloader version in structure shared by bootloader and main application, read from main application and sent out via CAN message when bootloader version is requested.
	LoaderData->bootloadervr_mnr = BOOTLOADERVR_MNR; 
WaitForBootCommand:
  command = 0;
  while(command != 128)                                    // Wait for CAN message 128.  It specifies the start mode:  if the 8 data bytes are {77, 46, 69, 46, 76, 101, 118, 105}
  {                                                        // then continue with the bootloader to download new firmware.  Otherwise jump to the application
    uint32_t curTicks = msTicks;                           // Capture the current value of the 1 ms tick count
    while(!CAN_RxRdy)                                      // Waiting for a CAN message to be received 
    {   
      if((msTicks - curTicks) > 2000)  jump2Appli();       // If command 128 is not received within 2000 msec, branch to fipos firmware
    }                                      
	  CAN_RxRdy = 0;
	  command = CAN_RxMsg.id &= 0xFF;                        // Capture the 8 LSB's of the message ID which is used as the command to the positioner
	  if (!(command==128&&CAN_RxMsg.data[0]==77&&CAN_RxMsg.data[1]==46&&CAN_RxMsg.data[2]==69&&CAN_RxMsg.data[3]==46
        &&CAN_RxMsg.data[4]==76&&CAN_RxMsg.data[5]==101&&CAN_RxMsg.data[6]==118&&CAN_RxMsg.data[7]==105))     
	  {
	    if (command==128)              
		  {
		    send_CANmsg(pos_id + 0x10000000, 8, 0x746F6F42, (BOOTLOADERVR_MNR << 24) + (BOOTLOADERVR_MJR << 16) + 0x00005746);         
                                                           // Send a CAN message with ID=pos_id, with data[i] = {'B', 'o', 'o', 't', 'F', 'W', BOOTFIRMWAREVR_MJR, BOOTFIRMWAREVR_MNR} to show bootloader is installed
		  }
	    jump2Appli();  		// If it is Command 128 but without the special code, then branch to fipos firmware
	  }
	}                                                        // If activation code was received, then continue and wait for command 129 which is the first command in the bootloading sequence
  send_CANmsg(pos_id + 0x10000000, 8, 0x04030201, 0x08070605);          // Send a CAN message with ID=pos_id, with data[i] = {1, 2, 3, 4, 5, 6, 7, 8} to show it is in bootloader mode
  while(command != 129)                                    // Bootloader waits for Command 129 to be received on the CAN bus
  {
    while(!CAN_RxRdy);                                     // Waiting for a CAN message to be received
    CAN_RxRdy = 0;
    command = CAN_RxMsg.id &= 0xFF;                        // Capture the 8 LSB's of the message ID which is used as the command to the positioner
    if (command == 129)                                    // If it is Command 129, then get the code_size as the low order 4 bytes in the message Data field
    {
      code_size = 0;
      code_size |= CAN_RxMsg.data[3];
      code_size |= CAN_RxMsg.data[2] << 8;
      code_size |= CAN_RxMsg.data[1] << 16;
      code_size |= CAN_RxMsg.data[0] << 24;
    }		
  }	
  command = 0;
  while(command != 130)
  {
    while(!CAN_RxRdy);                                     // Next wait for CAN message 130 which gives four bytes which is the number of parts in the code to be uploaded
    CAN_RxRdy = 0;
    command = CAN_RxMsg.id &= 0xFF;                        // Capture the 8 LSB's of the message ID which is used as the command to the positioner
    if (command == 130) 
    {
      number_of_parts = 0;                                 // If it is Command 130, then get the number_of_parts as the low order 4 bytes in the message Data field
      number_of_parts |= CAN_RxMsg.data[3];
      number_of_parts |= CAN_RxMsg.data[2] << 8;
      number_of_parts |= CAN_RxMsg.data[1] << 16;
      number_of_parts |= CAN_RxMsg.data[0] << 24;	
    }			
  }
//EraseFlash:                                              // Erases an interger number of Flash pages from Page 62 to Page 62 + code size in words 
  EraseFlashForApplication(APPLI_START_ADDR, APPLI_START_ADDR + 4*code_size); // Note that bootloader.h contains:	#define  APPLI_START_ADDR  ADDR_FLASH_PAGE_62
  for (n=0; n<number_of_parts; n++)
  {
//ReadyForPartN:
    for (p=0; p< buffer_size; p++)                         // p is the index of each packet (which is one 32 bit word) in the current AppliRxBuffer of data
    {                                                      // currentp is the index of each packet in the entire code, which typically consists of a number of buffer fulls of data
      while(!CAN_RxRdy);                                   // Wait for CAN message 132
      CAN_RxRdy = 0;
      command = CAN_RxMsg.id &= 0xFF;                      // Capture the 8 LSB's of the message ID which is used as the command to the positioner
      if (command != 132) 	ErrCnt[0] +=1;                 // We expect to get command 132 now so we count the extraneous commands we get?
      if (CAN_RxMsg.data[0] != (n+1)) ErrCnt[1] +=1;       // If the CAN message doesn't have the correct n+1 as data[0] we increment the error count?
      packet = 0;
      packet |= CAN_RxMsg.data[2];                         // CAN message data bytes 1 and 2 contain the packet number
      packet |= CAN_RxMsg.data[1] << 8;
      if (packet != p)   ErrCnt[2] +=1;                    // If the packet number is not as expected, increment the error counter
		
      AppliRxBuffer[p] = 0;                                // Read the word contained in bytes data[6] thru data[3] of the CAN message and put it into AppliRxBuffer[p]
      AppliRxBuffer[p] |= CAN_RxMsg.data[3];               // One 32 bit word is one Packet of data
      AppliRxBuffer[p] |= CAN_RxMsg.data[4] << 8; 
      AppliRxBuffer[p] |= CAN_RxMsg.data[5] << 16;
      AppliRxBuffer[p] |= CAN_RxMsg.data[6] << 24;
                                                           // Generate a checksum which is equal to the number of '1's in the word just read	<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<		
      word_sum = byte_sum[CAN_RxMsg.data[3]] + byte_sum[CAN_RxMsg.data[4]] + byte_sum[CAN_RxMsg.data[5]] + byte_sum[CAN_RxMsg.data[6]];
                                                           // byte data[7] will contain the same checksum to verify the data were receceived correctly
      if (word_sum != CAN_RxMsg.data[7]) ErrCnt[3] +=1;    // If the checksum doesn't match, increment the error_count
      if (currentp >= (code_size-1))                       // Break out of the loop when the last "Part" is not a full buffer
      {
        currentp = p;                                      // To capture the point in the last buffer where the code ends and we want to fill it with zeros	
        p = (buffer_size);                                 // To break out of the loop
      }			
      currentp += 1;                                       // currentp is incremented each time the loop executes so it indexes every packet (word) in the full code
    } //end for buffer_size. Part n is now complete
      //for (i=currentp; i< buffer_size; i++)  AppliRxBuffer[i] = 0xFFFFFFFF; // This will fill default erase value into the rest of the AppliRxBuffer which does not have code in it
      write_operations = WriteRxBuffer(APPLI_START_ADDR + n*4*buffer_size, currentp); // write buffer to flash and verify number of write operations 
      if (write_operations != currentp) ErrCnt[4] +=1;  // The number of write operations to the Flash Memory should be equal to buffer_size
  }
                                                           // At this point all of the fipos application code has been written into the Flash Memory		
  command = 0;                                             // Now a final verification command (command 131) is sent from the Petal Controller
  while (command != 131)                                   // Wait for the final verification command
  {
    while (!CAN_RxRdy);
    CAN_RxRdy = 0;
    command = CAN_RxMsg.id &= 0xFF;                        // Capture the 8 LSB's of the message ID which is used as the command to the positioner
    if (command == 131)
    {
      if((ErrCnt[0] | ErrCnt[1] | ErrCnt[2] | ErrCnt[3] | ErrCnt[4]) == 0) // Check if there are any errors
      {
        send_CANmsg(pos_id + 0x10000000, 1, 1, 0);                      // If no errors, send a CAN message with ID=pos_id, with 1 data byte which contains 0x01
        jump2Appli();                                      // Then jump to the application
      }
      else                                                 // If there are any errors, send a message giving the 8 LSB's of each kind of error count
      {
        send_CANmsg(pos_id + 0x10000000, 8, 0+((255&ErrCnt[0])<<8)+((255&ErrCnt[1])<<16)+((255&ErrCnt[2])<<24), (255&ErrCnt[3])+((255&ErrCnt[4])<<8)); // If there were any errors, send a CAN message with ID=pos_id, with 1 data byte which contains 0x00                                                                
        // The data bytes as shown by candump on the Beagle Bone will be (from left to right): 00, ErrCnt[0], ErrCnt[1], ErrCnt[2], ErrCnt[3], ErrCnt[4], 00, 00
        EraseFlashForApplication(APPLI_START_ADDR, APPLI_START_ADDR + 4*code_size);
        goto WaitForBootCommand;                           // Then erase the entire fipos code area, and if sync is high, wait for a new program to be downloaded
      }                                                    
    }
  }	
}                                                          // end main

