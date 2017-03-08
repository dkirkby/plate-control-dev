#include "custom_flash_functions.h"

extern uint32_t		statusReg;
extern uint32_t 	buffer_size;
extern uint32_t 	AppliRxBuffer[];

pFunction JumpToApplication;
uint32_t JumpAddress;


/**
  * @brief Erase Flash blocks for Application from Start_Address to End_Address
  * @param Start_Address, End_Address
  * @retval
  */
void EraseFlashForApplication(uint32_t Start_Address, uint32_t End_Address){
	uint32_t 					StartPage = 0;
	uint32_t 					EndPage = 0;
	uint32_t 					i = 0;

	// If we didn't start already we will erase. This avoids erasing multiple times.
	if(1/*~statusReg & FLASH_RW_Start*/){
		
		FLASH_Unlock();
		FLASH_ClearFlag(FLASH_FLAG_BSY | FLASH_FLAG_EOP | FLASH_FLAG_PGERR | FLASH_FLAG_WRPRTERR | FLASH_FLAG_OPTERR); 
		StartPage = GetFlashPage(Start_Address);
		EndPage 	= GetFlashPage(End_Address);	

	/* Erase Pages. Device voltage range supposed to be [2.7V to 3.6V], the operation will be done by word */
		for(i=StartPage; i<=EndPage; i+=2048){ 					// 2048 is the size of a page in bytes. => increment the address by 2048 points to the next page.
			if (FLASH_ErasePage(i) != FLASH_COMPLETE){ 
				while (1){} /* Error occurred while erasing Flash memory. User can add here some code to deal with this error */
			}
		}
		statusReg |= FLASH_RW_Start;
		FLASH_Lock();
	}
}

	/**
  * @brief Write Application from Application Buffer
  * @param Start_Address
  * @retval
  */
uint32_t WriteRxBuffer(uint32_t Start_Address){
	static uint32_t 	WriteOperationCount = 0;
	static uint32_t 	CurentAddress = 0;
  uint32_t					i = 0;
	WriteOperationCount = 0;
	
	if(1/*~statusReg & READY_TO_RUN_APP*/){ // if not ready to run app we will now write code to flash
	  
		CurentAddress = Start_Address;
		i = 0;
		
		FLASH_Unlock();
		FLASH_ClearFlag(FLASH_FLAG_BSY | FLASH_FLAG_EOP | FLASH_FLAG_PGERR | FLASH_FLAG_WRPRTERR | FLASH_FLAG_OPTERR); 
		while (i < buffer_size){
			if (FLASH_ProgramWord(CurentAddress, AppliRxBuffer[i]) == FLASH_COMPLETE){
				CurentAddress = CurentAddress + 4; //increment the address by one word
				i++;
				WriteOperationCount++;
			}else{
					while(1){}
			}
		} 
		FLASH_Lock();
		statusReg |= (FLASH_RW_Stop|READY_TO_RUN_APP);
	}
	return WriteOperationCount;
}


/**
  * @brief  Jump to application
  * @param  
  * @retval 
  */
void jump2Appli(){
		JumpAddress = *(__IO uint32_t*) (APPLI_START_ADDR + 4);
		JumpToApplication = (pFunction) JumpAddress;
		/* Initialize user application's Stack Pointer */
		__set_MSP(*(__IO uint32_t*) APPLI_START_ADDR);
		JumpToApplication();
}
//END jump2Appli



/**
  * @brief  Get Flash Page 
  * @param  Address
  * @retval Page
  */
uint32_t GetFlashPage(uint32_t Address){
				return ((Address - ADDR_FLASH_PAGE_0)/(1<<11))*(1<<11) + ADDR_FLASH_PAGE_0;
}
//END GetFlashPage
